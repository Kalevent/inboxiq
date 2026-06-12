"""
DSPy Module Compilation

Compiles DSPy modules using training data for optimal prompt generation.
Saves compiled artifacts to dspy_artifacts/ directory.

Usage:
    python -m src.dspy.training.compile_modules --module visitor_qualification
    python -m src.dspy.training.compile_modules --module all
"""
import os
import sys
import json
import pickle
import argparse
from typing import List

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

import dspy
from dspy.teleprompt import BootstrapFewShot

from src.dspy.funnel import (
    VisitorQualificationModule,
    InterestScoringModule
)

from src.dspy.content import (
    TopicGeneratorModule
)


def load_training_data(file_path: str) -> List[dspy.Example]:
    """
    Load training data from JSONL file and convert to DSPy examples.

    Args:
        file_path: Path to JSONL training data file

    Returns:
        List of DSPy Example objects
    """
    examples = []

    with open(file_path, 'r') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                examples.append(dspy.Example(**data).with_inputs(*list(data.keys())))

    return examples


def compile_visitor_qualification(training_data_path: str, output_dir: str):
    """
    Compile VisitorQualificationModule using BootstrapFewShot.

    Args:
        training_data_path: Path to training data file
        output_dir: Directory to save compiled artifact
    """
    print("\n" + "="*60)
    print("Compiling VisitorQualificationModule")
    print("="*60)

    # Load training data
    trainset = load_training_data(training_data_path)
    print(f"Loaded {len(trainset)} training examples")

    # Initialize module
    module = VisitorQualificationModule()

    # Define evaluation metric
    def fit_score_accuracy(example, pred, trace=None):
        """Evaluate fit score accuracy (within ±2 points)."""
        try:
            true_score = int(example.fit_score)
            pred_score = int(pred.fit_score)
            return abs(true_score - pred_score) <= 2
        except:
            return False

    # Compile using BootstrapFewShot
    config = dict(max_bootstrapped_demos=8, max_labeled_demos=8)
    teleprompter = BootstrapFewShot(metric=fit_score_accuracy, **config)

    print("Compiling module (this may take a few minutes)...")
    compiled_module = teleprompter.compile(module, trainset=trainset)

    # Save compiled module
    output_path = os.path.join(output_dir, "visitor_qualification_compiled.pkl")
    with open(output_path, 'wb') as f:
        pickle.dump(compiled_module, f)

    print(f"✓ Compiled module saved to {output_path}")

    return compiled_module


def compile_interest_scoring(training_data_path: str, output_dir: str):
    """
    Compile InterestScoringModule using BootstrapFewShot.
    """
    print("\n" + "="*60)
    print("Compiling InterestScoringModule")
    print("="*60)

    trainset = load_training_data(training_data_path)
    print(f"Loaded {len(trainset)} training examples")

    module = InterestScoringModule()

    def intent_score_accuracy(example, pred, trace=None):
        """Evaluate intent score accuracy (within ±2 points)."""
        try:
            true_score = int(example.intent_score)
            pred_score = int(pred.intent_score)
            return abs(true_score - pred_score) <= 2
        except:
            return False

    config = dict(max_bootstrapped_demos=6, max_labeled_demos=6)
    teleprompter = BootstrapFewShot(metric=intent_score_accuracy, **config)

    print("Compiling module...")
    compiled_module = teleprompter.compile(module, trainset=trainset)

    output_path = os.path.join(output_dir, "interest_scoring_compiled.pkl")
    with open(output_path, 'wb') as f:
        pickle.dump(compiled_module, f)

    print(f"✓ Compiled module saved to {output_path}")

    return compiled_module


def compile_topic_generator(training_data_path: str, output_dir: str):
    """
    Compile TopicGeneratorModule using BootstrapFewShot.
    """
    print("\n" + "="*60)
    print("Compiling TopicGeneratorModule")
    print("="*60)

    trainset = load_training_data(training_data_path)
    print(f"Loaded {len(trainset)} training examples")

    module = TopicGeneratorModule()

    def topic_quality(example, pred, trace=None):
        """Simple quality check: topics should be valid JSON."""
        try:
            topics = json.loads(pred.topics)
            return len(topics) > 0 and all('title' in t for t in topics)
        except:
            return False

    config = dict(max_bootstrapped_demos=5, max_labeled_demos=5)
    teleprompter = BootstrapFewShot(metric=topic_quality, **config)

    print("Compiling module...")
    compiled_module = teleprompter.compile(module, trainset=trainset)

    output_path = os.path.join(output_dir, "topic_generator_compiled.pkl")
    with open(output_path, 'wb') as f:
        pickle.dump(compiled_module, f)

    print(f"✓ Compiled module saved to {output_path}")

    return compiled_module


def compile_all_modules(training_data_dir: str = "./training_data",
                       output_dir: str = "./dspy_artifacts"):
    """
    Compile all DSPy modules.

    Args:
        training_data_dir: Directory containing training data files
        output_dir: Directory to save compiled artifacts
    """
    os.makedirs(output_dir, exist_ok=True)

    # Configure DSPy
    lm = dspy.OpenAI(model=os.getenv("DSPY_MODEL", "gpt-4"), max_tokens=2000)
    dspy.settings.configure(lm=lm)

    print("\n" + "="*60)
    print("DSPy Module Compilation")
    print("="*60)

    compiled = []

    # Compile funnel modules
    try:
        visitor_qual_path = os.path.join(training_data_dir, "visitor_qualification_training.jsonl")
        if os.path.exists(visitor_qual_path):
            compiled.append(compile_visitor_qualification(visitor_qual_path, output_dir))
        else:
            print(f"⚠ Training data not found: {visitor_qual_path}")
    except Exception as e:
        print(f"✗ Failed to compile visitor_qualification: {e}")

    try:
        interest_path = os.path.join(training_data_dir, "interest_scoring_training.jsonl")
        if os.path.exists(interest_path):
            compiled.append(compile_interest_scoring(interest_path, output_dir))
        else:
            print(f"⚠ Training data not found: {interest_path}")
    except Exception as e:
        print(f"✗ Failed to compile interest_scoring: {e}")

    # Compile content modules
    try:
        topic_path = os.path.join(training_data_dir, "topic_generator_training.jsonl")
        if os.path.exists(topic_path):
            compiled.append(compile_topic_generator(topic_path, output_dir))
        else:
            print(f"⚠ Training data not found: {topic_path}")
    except Exception as e:
        print(f"✗ Failed to compile topic_generator: {e}")

    print("\n" + "="*60)
    print(f"Compilation complete! {len(compiled)} modules compiled.")
    print(f"Artifacts saved to: {output_dir}")
    print("="*60 + "\n")

    return compiled


def main():
    parser = argparse.ArgumentParser(description='Compile DSPy modules')
    parser.add_argument('--module', type=str, default='all',
                       help='Module to compile (visitor_qualification, interest_scoring, topic_generator, or all)')
    parser.add_argument('--training-data-dir', type=str, default='./training_data',
                       help='Directory containing training data')
    parser.add_argument('--output-dir', type=str, default='./dspy_artifacts',
                       help='Output directory for compiled artifacts')

    args = parser.parse_args()

    # Configure DSPy
    lm = dspy.OpenAI(model=os.getenv("DSPY_MODEL", "gpt-4"), max_tokens=2000)
    dspy.settings.configure(lm=lm)

    if args.module == 'all':
        compile_all_modules(args.training_data_dir, args.output_dir)
    elif args.module == 'visitor_qualification':
        training_path = os.path.join(args.training_data_dir, "visitor_qualification_training.jsonl")
        compile_visitor_qualification(training_path, args.output_dir)
    elif args.module == 'interest_scoring':
        training_path = os.path.join(args.training_data_dir, "interest_scoring_training.jsonl")
        compile_interest_scoring(training_path, args.output_dir)
    elif args.module == 'topic_generator':
        training_path = os.path.join(args.training_data_dir, "topic_generator_training.jsonl")
        compile_topic_generator(training_path, args.output_dir)
    else:
        print(f"Unknown module: {args.module}")
        sys.exit(1)


if __name__ == "__main__":
    main()
