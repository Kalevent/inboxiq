"""
Tool-Calling Automation Agent - Like Claude Code!

This agent has:
- Dynamic tool calling (not pre-defined action handlers)
- Agent loops (continues until workflow complete)
- Multi-step reasoning (can plan and execute complex workflows)
- Error recovery (tries alternatives when things fail)
- Full autonomy (figures out how to accomplish goals)

This is TRUE agentic automation - not just structured LLM outputs!
"""

from __future__ import annotations

import os
import json
import logging
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from uuid import uuid4

from openai import OpenAI

from src.models import AutomationRule, WebhookProvider, AutomationRuleExecution
from src.extensions import db

logger = logging.getLogger(__name__)


class ToolCallingAutomationAgent:
    """
    Tool-calling agent with dynamic tool selection and agent loops.

    Works like Claude Code - has tools and uses them autonomously to accomplish workflows!
    """

    def __init__(self, workflow: AutomationRule, trigger_context: Dict[str, Any]):
        self.workflow = workflow
        self.trigger_context = trigger_context
        self.account_id = workflow.account_id
        self.execution_log: List[str] = []
        self.tool_calls: List[Dict[str, Any]] = []

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY required for tool-calling agent")

        self.openai = OpenAI(api_key=api_key)

        # Register available tools
        self.tools = self._register_tools()
        self.tool_handlers = self._register_tool_handlers()

    def _register_tools(self) -> List[Dict[str, Any]]:
        """Register tools the agent can call dynamically."""
        return [
            {
                "type": "function",
                "function": {
                    "type": "function",
                    "function": {
                        "name": "search_webhook_providers",
                        "description": "Search for webhook providers by name or type (slack, teams, sage, quickbooks, custom). Returns list of available providers with IDs.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query (provider name or type like 'slack', 'teams')"
                                }
                            },
                            "required": ["query"]
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_webhook",
                    "description": "Send a webhook request to a provider. Use this to send notifications to Slack, Teams, or custom webhooks.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "provider_id": {
                                "type": "string",
                                "description": "UUID of the webhook provider (get from search_webhook_providers)"
                            },
                            "payload": {
                                "type": "object",
                                "description": "Payload to send (for Slack: {text, channel, username, icon_emoji})"
                            }
                        },
                        "required": ["provider_id", "payload"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_context_field",
                    "description": "Search for a field in the trigger context. Use this to find email subject, body, ticket data, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "field_path": {
                                "type": "string",
                                "description": "Dot-notation path to field (e.g., 'email.subject', 'ticket.priority')"
                            }
                        },
                        "required": ["field_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "evaluate_condition",
                    "description": "Evaluate a condition against context data. Returns true/false.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "field_path": {
                                "type": "string",
                                "description": "Path to field in context"
                            },
                            "operator": {
                                "type": "string",
                                "enum": ["equals", "contains", "not_contains", "greater_than", "less_than", "is_empty", "is_not_empty"],
                                "description": "Comparison operator"
                            },
                            "value": {
                                "type": "string",
                                "description": "Value to compare against"
                            }
                        },
                        "required": ["field_path", "operator", "value"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "render_template",
                    "description": "Render a template string with context variables. Use {{variable}} syntax.",
                }
                "parameters": {
                    "type": "object",
                    "properties": {
                        "template": {
                            "type": "string",
                            "description": "Template string with {{variables}}"
                        }
                    },
                    "required": ["template"]
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_context_summary",
                    "description": "Get a summary of all available context data (email, ticket, extracted fields).",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]

    def _register_tool_handlers(self) -> Dict[str, Callable]:
        """Map tool names to their implementation functions."""
        return {
            "search_webhook_providers": self._tool_search_webhook_providers,
            "send_webhook": self._tool_send_webhook,
            "search_context_field": self._tool_search_context_field,
            "evaluate_condition": self._tool_evaluate_condition,
            "render_template": self._tool_render_template,
            "get_context_summary": self._tool_get_context_summary
        }

    def execute(self, trigger_event: str) -> Dict[str, Any]:
        """
        Execute workflow using agent loop with tool calling.

        The agent will:
        1. Understand the workflow
        2. Use tools to gather information
        3. Evaluate conditions with tools
        4. Execute actions with tools
        5. Handle errors and try alternatives
        6. Loop until complete
        """
        self.log("🤖 Starting tool-calling agent execution")

        # Build initial prompt for agent
        initial_prompt = self._build_initial_prompt()

        # Initialize conversation
        messages = [
            {
                "role": "user",
                "content": initial_prompt
            }
        ]

        try:
            # Agent loop - continues until agent says it's done
            max_iterations = 20
            iteration = 0

            while iteration < max_iterations:
                iteration += 1
                self.log(f"🔄 Agent iteration {iteration}")

                # Call OpenAI with tools
                response = self.openai.chat.completions.create(
                    model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    max_tokens=4096,
                    tools=self.tools,
                    messages=messages
                )

                message = response.choices[0].message

                # Log agent's thinking
                if message.content:
                    self.log(f"💭 Agent: {message.content[:200]}...")

                # Check if agent wants to use tools
                if message.tool_calls:
                    # Agent called tools - execute them
                    tool_results = []

                    for tool_call in message.tool_calls:
                        self.log(f"🔧 Agent calling tool: {tool_call.function.name}")

                        # Parse tool arguments
                        tool_args = json.loads(tool_call.function.arguments)

                        # Execute the tool
                        result = self._execute_tool(tool_call.function.name, tool_args)

                        self.tool_calls.append({
                            "tool": tool_call.function.name,
                            "input": tool_args,
                            "result": result
                        })

                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result)
                        })

                    # Add assistant's message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": message.tool_calls
                    })

                    # Add tool results
                    messages.extend(tool_results)

                    # Continue loop - agent will process results and decide next steps
                    continue

                else:
                    # Agent is done (no tool calls)
                    self.log("✅ Agent completed workflow")

                    final_text = message.content or ""

                    # Parse success from agent's response
                    success = "success" in final_text.lower() and "fail" not in final_text.lower()

                    self._store_execution(
                        trigger_event=trigger_event,
                        matched=True,
                        executed=True,
                        success=success,
                        agent_response=final_text
                    )

                    return {
                        "executed": True,
                        "matched": True,
                        "success": success,
                        "agent_log": self.execution_log,
                        "tool_calls": self.tool_calls,
                        "agent_response": final_text
                    }

                else:
                    # Unexpected stop reason
                    self.log(f"⚠️  Unexpected stop reason: {response.stop_reason}")
                    break

            # Max iterations reached
            self.log("⚠️  Max iterations reached")
            return {
                "executed": True,
                "matched": True,
                "success": False,
                "error": "Max iterations reached",
                "agent_log": self.execution_log,
                "tool_calls": self.tool_calls
            }

        except Exception as e:
            logger.exception(f"Tool-calling agent failed: {e}")
            self.log(f"❌ Error: {str(e)}")

            self._store_execution(
                trigger_event=trigger_event,
                matched=True,
                executed=False,
                success=False,
                error_message=str(e)
            )

            return {
                "executed": False,
                "matched": True,
                "success": False,
                "error": str(e),
                "agent_log": self.execution_log
            }

    def _build_initial_prompt(self) -> str:
        """Build initial prompt for the agent."""
        return f"""You are an intelligent automation agent executing a workflow. Your goal is to accomplish the workflow using the available tools.

**WORKFLOW TO EXECUTE:**
Name: {self.workflow.name}
Description: {self.workflow.description or "N/A"}

Trigger: {json.dumps(self.workflow.trigger, indent=2)}
Conditions: {json.dumps(self.workflow.conditions, indent=2)}
Condition Logic: {self.workflow.condition_logic}
Actions: {json.dumps(self.workflow.actions, indent=2)}

**YOUR TASK:**
1. Use get_context_summary to understand available data
2. Use search_context_field and evaluate_condition to check if conditions are met
3. If conditions are NOT met, respond with "Conditions not met, workflow skipped"
4. If conditions ARE met, execute the actions using appropriate tools:
   - For webhook/Slack actions: use search_webhook_providers then send_webhook
   - For template rendering: use render_template
   - For data lookup: use search_context_field

5. When done, respond with "Workflow execution completed successfully" or "Workflow execution failed: [reason]"

**IMPORTANT:**
- Use tools to accomplish tasks, don't just describe what you would do
- Call multiple tools as needed to complete the workflow
- If something fails, try alternative approaches
- Be autonomous - figure out how to accomplish the goal

Start by using get_context_summary to see what data is available."""

    def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """Execute a tool and return its result."""
        handler = self.tool_handlers.get(tool_name)

        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            result = handler(**tool_input)
            self.log(f"✅ Tool {tool_name} succeeded")
            return result
        except Exception as e:
            logger.exception(f"Tool {tool_name} failed: {e}")
            self.log(f"❌ Tool {tool_name} failed: {e}")
            return {"error": str(e)}

    # =========================================================================
    # Tool Implementations
    # =========================================================================

    def _tool_search_webhook_providers(self, query: str) -> List[Dict[str, Any]]:
        """Search for webhook providers."""
        query_lower = query.lower()

        providers = WebhookProvider.query.filter_by(
            account_id=self.account_id,
            enabled=True
        ).all()

        # Filter by query
        results = []
        for p in providers:
            if (query_lower in p.configuration_name.lower() or
                query_lower in p.provider_type.lower()):
                results.append({
                    "id": str(p.id),
                    "type": "function",
                    "function": {
                        "name": p.configuration_name,
                        "type": p.provider_type
                    })
                    }

        return results

    def _tool_send_webhook(self, provider_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send webhook using existing action handler."""
        from src.automation.actions import execute_action

        config = {
            "provider": provider_id,
            "payload_template": payload
        }

        result = execute_action("send_webhook", self.trigger_context, config)
        return result

    def _tool_search_context_field(self, field_path: str) -> Any:
        """Search for a field in context."""
        parts = field_path.split(".")
        current = self.trigger_context

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return {"error": f"Field not found: {field_path}"}

            if current is None:
                return {"error": f"Field not found: {field_path}"}

        return {"value": current, "found": True}

    def _tool_evaluate_condition(self, field_path: str, operator: str, value: str) -> Dict[str, Any]:
        """Evaluate a condition."""
        field_result = self._tool_search_context_field(field_path)

        if "error" in field_result:
            return {"matched": False, "error": field_result["error"]}

        actual = field_result["value"]

        try:
            if operator == "equals":
                matched = str(actual) == str(value)
            elif operator == "contains":
                matched = str(value).lower() in str(actual).lower()
            elif operator == "not_contains":
                matched = str(value).lower() not in str(actual).lower()
            elif operator == "greater_than":
                matched = float(actual) > float(value)
            elif operator == "less_than":
                matched = float(actual) < float(value)
            elif operator == "is_empty":
                matched = not actual
            elif operator == "is_not_empty":
                matched = bool(actual)
            else:
                return {"matched": False, "error": f"Unknown operator: {operator}"}

            return {
                "matched": matched,
                "actual_value": actual,
                "expected_value": value,
                "operator": operator
            }
        except Exception as e:
            return {"matched": False, "error": str(e)}

    def _tool_render_template(self, template: str) -> Dict[str, Any]:
        """Render a template with context variables."""
        from src.automation.template_engine import render_template, build_context

        context = build_context(
            email=self.trigger_context.get("email"),
            extracted=self.trigger_context.get("extracted"),
            ticket=self.trigger_context.get("ticket"),
            lead=self.trigger_context.get("lead"),
            account_id=self.account_id,
            rule_name=self.workflow.name
        )

        try:
            rendered = render_template(template, context)
            return {"rendered": rendered}
        except Exception as e:
            return {"error": str(e)}

    def _tool_get_context_summary(self) -> Dict[str, Any]:
        """Get summary of available context."""
        summary = {
            "available_fields": []
        }

        if "email" in self.trigger_context:
            email = self.trigger_context["email"]
            summary["email"] = {
                "subject": email.get("subject", "")[:100],
                "from": email.get("from_email", ""),
                "has_body": bool(email.get("body"))
            }
            summary["available_fields"].extend([
                "email.subject",
                "email.body",
                "email.from_email",
                "email.provider"
            ])

        if "ticket" in self.trigger_context:
            ticket = self.trigger_context["ticket"]
            summary["ticket"] = {}
            if isinstance(ticket, dict):
                summary["ticket"] = {k: str(v)[:100] for k, v in ticket.items() if k != "body"}
            summary["available_fields"].extend([
                "ticket.category",
                "ticket.priority",
                "ticket.status"
            ])

        if "extracted" in self.trigger_context:
            extracted = self.trigger_context["extracted"]
            if isinstance(extracted, dict):
                summary["extracted_fields"] = list(extracted.keys())
                summary["available_fields"].extend([f"extracted.{k}" for k in extracted.keys()])

        return summary

    def _store_execution(
        self,
        trigger_event: str,
        matched: bool,
        executed: bool,
        success: bool,
        agent_response: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Store execution record."""
        from src.observability_sanitizer import sanitize_trigger_context

        # Extract ticket/lead IDs
        ticket_id = None
        lead_id = None

        if "ticket" in self.trigger_context:
            ticket = self.trigger_context["ticket"]
            if isinstance(ticket, dict):
                ticket_id = ticket.get("id")
            elif hasattr(ticket, "id"):
                ticket_id = ticket.id

        if "lead" in self.trigger_context:
            lead = self.trigger_context["lead"]
            if isinstance(lead, dict):
                lead_id = lead.get("id")
            elif hasattr(lead, "id"):
                lead_id = lead.id

        execution = AutomationRuleExecution(
            id=str(uuid4()),
            rule_id=self.workflow.id,
            account_id=self.account_id,
            trace_id="agent-" + str(uuid4())[:8],
            ticket_id=ticket_id,
            lead_id=lead_id,
            trigger_event=trigger_event,
            trigger_type=self.trigger_context.get("type", "email"),
            trigger_context=sanitize_trigger_context(self.trigger_context),
            matched=matched,
            executed=executed,
            success=success,
            error_message=error_message or agent_response,
            execution_time_ms=0,
            conditions_evaluated=None,
            actions_executed=[{"type": "agent_loop", "tool_calls": len(self.tool_calls)}]
        )

        db.session.add(execution)

        # Update workflow stats
        self.workflow.execution_count = (self.workflow.execution_count or 0) + 1
        if success:
            self.workflow.success_count = (self.workflow.success_count or 0) + 1
        if error_message:
            self.workflow.error_count = (self.workflow.error_count or 0) + 1
        self.workflow.last_executed_at = datetime.utcnow()

        db.session.commit()

    def log(self, message: str):
        """Add message to execution log."""
        self.execution_log.append(message)
        logger.info(f"[ToolCallingAgent {self.workflow.name}] {message}")


def execute_workflow_with_tool_calling_agent(
    workflow_id: str,
    trigger_context: Dict[str, Any],
    trigger_event: str = "unknown"
) -> Dict[str, Any]:
    """
    Execute workflow using tool-calling agent with dynamic tool selection.

    This is TRUE agentic automation - like Claude Code!
    """
    workflow = AutomationRule.query.filter_by(id=workflow_id).first()

    if not workflow:
        return {"executed": False, "error": "Workflow not found"}

    if not workflow.enabled:
        return {"executed": False, "reason": "workflow_disabled"}

    # Create tool-calling agent
    agent = ToolCallingAutomationAgent(workflow, trigger_context)
    return agent.execute(trigger_event)
