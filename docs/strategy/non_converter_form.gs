/**
 * Non-Converter Feedback Form
 *
 * How to use:
 * 1. Go to https://script.google.com
 * 2. Create a new project, name it "Non-Converter Feedback"
 * 3. Paste this file, replacing the default code
 * 4. Run → createFeedbackForm
 * 5. Copy the Share link from the Execution log
 * 6. Paste into the re-engagement email
 */

function createFeedbackForm() {
  const form = FormApp.create('Quick feedback — InboxIQ');

  form.setDescription(
    'Four questions. Takes about 90 seconds. ' +
    'No sales follow-up unless you ask for one.'
  );

  form.setCollectEmail(false);
  form.setProgressBar(false);

  // Q1 — Did they understand what InboxIQ does?
  form.addMultipleChoiceItem()
    .setTitle('When you saw the email about InboxIQ, what was your honest reaction?')
    .setChoiceValues([
      'Interesting — but not relevant to me right now',
      'Relevant problem, but I wasn\'t convinced this solves it',
      'Relevant problem, but the price wasn\'t right',
      'I already have something that does this',
      'I didn\'t fully understand what it does',
      'I meant to sign up and just forgot'
    ])
    .setRequired(true);

  // Q2 — What is actually blocking them
  form.addParagraphTextItem()
    .setTitle('What would have made you sign up?')
    .setHelpText('Be blunt — this goes directly to the founder.')
    .setRequired(false);

  // Q3 — Validate the problem exists at all
  form.addMultipleChoiceItem()
    .setTitle('Do you currently manage a shared inbox — support@, info@, or similar?')
    .setChoiceValues([
      'Yes — it\'s a real pain point',
      'Yes — but it\'s manageable',
      'No — I manage my own inbox only',
      'Not yet, but we\'re growing into it'
    ])
    .setRequired(true);

  // Q4 — Open door for a call
  form.addMultipleChoiceItem()
    .setTitle('Would you be open to a 15-minute call? No pitch — just a conversation.')
    .setChoiceValues([
      'Yes — happy to talk',
      'Maybe — email me first',
      'No thanks'
    ])
    .setRequired(true);

  form.setConfirmationMessage(
    'Thank you — this is genuinely useful. ' +
    'If you said yes to a call, I\'ll be in touch within 48 hours.'
  );

  const url = form.getPublishedUrl();
  Logger.log('Form created successfully.');
  Logger.log('Share this link: ' + url);
  Logger.log('Edit the form at: ' + form.getEditUrl());
}
