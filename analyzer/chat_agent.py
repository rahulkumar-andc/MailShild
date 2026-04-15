import json
import logging
from datetime import timedelta
from django.utils import timezone
from groq import Groq
from django.conf import settings
from .models import Message, Reminder, FavouriteUser
from dateutil import parser as dateutil_parser

logger = logging.getLogger(__name__)

# ==========================================
# TOOL IMPLEMENTATIONS (Python Wrappers)
# ==========================================

def get_recent_summary():
    """Fetches recent data and formats it into a summary string."""
    cutoff = timezone.now() - timedelta(days=3)
    recent_messages = Message.objects.filter(received_at__gte=cutoff).order_by('-received_at')[:15]
    upcoming_reminders = Reminder.objects.filter(is_sent=False, remind_at__gte=timezone.now()).order_by('remind_at')[:10]
    
    context_lines = []
    
    if upcoming_reminders.exists():
        context_lines.append("--- UPCOMING REMINDERS/DEADLINES ---")
        for r in upcoming_reminders:
            context_lines.append(f"Reminder: {r.title} | Due: {r.remind_at.strftime('%Y-%m-%d %H:%M:%S')} | Details: {r.description}")
        context_lines.append("")
        
    if recent_messages.exists():
        context_lines.append("--- RECENT MESSAGES (Last 3 Days) ---")
        for m in recent_messages:
            context_lines.append(f"[{m.received_at.strftime('%Y-%m-%d %H:%M:%S')}] From: {m.sender} via {m.source.upper()}")
            context_lines.append(f"Subject/Group: {m.subject}")
            context_lines.append(f"Summary/Category: {m.category}")
            context_lines.append("---")
            
    if not context_lines:
        return "No recent messages or upcoming reminders."
        
    return "\n".join(context_lines)

def delete_all_spam():
    """Deletes all messages currently marked as SPAM."""
    spam_msgs = Message.objects.filter(category='SPAM')
    count = spam_msgs.count()
    spam_msgs.delete()
    return f"Successfully deleted {count} spam messages from the database."

def add_favourite(username, source="instagram"):
    """Adds a user to the Favourites list to bypass AI classification."""
    obj, created = FavouriteUser.objects.get_or_create(username=username, defaults={'source': source})
    if created:
        return f"Success: Added {username} to Favourites."
    return f"Info: {username} is already in Favourites."

def create_reminder(title, description, raw_time):
    """Creates a new manual reminder. raw_time should be ISO format if possible."""
    try:
        remind_at = dateutil_parser.parse(raw_time)
        if remind_at.tzinfo is None:
            remind_at = timezone.make_aware(remind_at)
            
        if remind_at <= timezone.now():
            return "Error: Cannot create a reminder in the past."
            
        Reminder.objects.create(
            title=title,
            description=description,
            remind_at=remind_at,
            is_sent=False,
            source='system'
        )
        return f"Successfully created reminder '{title}' for {remind_at.strftime('%Y-%m-%d %H:%M:%S')}"
    except Exception as e:
        return f"Error creating reminder: Could not parse time '{raw_time}'. Exception: {e}"

def send_whatsapp_message(target, message, dry_run=False):
    """
    Sends an outbound WhatsApp message. 
    target can be a JID (like 1203xxx@g.us) or a known group name.
    """
    import requests
    from .models import MonitoredWhatsAppGroup
    
    # 1. Resolve JID if a name was provided
    jid = target
    
    # Check if it's a phone number (10+ digits, no @)
    import re
    digits_only = re.sub(r'\D', '', target)
    if '@' not in target and len(digits_only) >= 10:
        # If it's a number, standard WhatsApp format is country_code + number + @c.us
        # Assuming Indian numbers if no country code provided (starting with 6-9)
        if len(digits_only) == 10:
            jid = f"91{digits_only}@c.us"
        else:
            jid = f"{digits_only}@c.us"
            
    elif '@' not in target:
        # Search for group by name
        # Try exact first, then icontains
        group = MonitoredWhatsAppGroup.objects.filter(group_name__iexact=target).first()
        if not group:
            group = MonitoredWhatsAppGroup.objects.filter(group_name__icontains=target).first()
            
        if group:
            jid = group.group_id
        else:
            # If still not found, list available groups to help the user
            all_groups = MonitoredWhatsAppGroup.objects.all()
            group_list_str = ", ".join([g.group_name for g in all_groups]) if all_groups.exists() else "None"
            return f"Error: Could not find a group matching '{target}'. \nMonitored groups are: {group_list_str}. \nPlease use the exact name or JID."

    if dry_run:
        return f"[DRY RUN] Message would be sent to {jid}: {message}"

    # 2. Call Bridge API
    BRIDGE_URL = "http://127.0.0.1:3001/send"
    SECRET = "mailshield-wa-secret-2026"
    
    try:
        payload = {
            "secret": SECRET,
            "target": jid,
            "message": message
        }
        response = requests.post(BRIDGE_URL, json=payload, timeout=15)
        
        if response.status_code == 200:
            return f"Success: Message sent to {target} ({jid})."
        elif response.status_code == 429:
            return f"Rate Limit Error: {response.json().get('error')}"
        else:
            return f"Failed to send message: {response.text}"
            
    except Exception as e:
        return f"Connection Error: Could not reach WhatsApp Bridge. Error: {e}"

def search_messages(query=None, sender=None, limit=10):
    """Search the database for specific messages."""
    from .models import Message
    from django.db.models import Q
    
    qs = Message.objects.all()
    if sender:
        qs = qs.filter(sender__icontains=sender)
    if query:
        qs = qs.filter(Q(body__icontains=query) | Q(subject__icontains=query))
        
    results = qs.order_by('-received_at')[:limit]
    if not results.exists():
        return "No matching messages found."
        
    lines = []
    for m in results:
        lines.append(f"[{m.received_at}] From: {m.sender} | Body: {m.body[:150]}...")
    return "\n".join(lines)

def get_all_senders():
    """List unique senders and sources in the database."""
    from .models import Message
    senders = Message.objects.values('sender', 'source').distinct()[:30]
    if not senders:
        return "Database is empty."
    
    lines = ["Found these senders:"]
    for s in senders:
        lines.append(f"- {s['sender']} ({s['source']})")
    return "\n".join(lines)

def get_latest_news():
    """Fetch recent security threats/news."""
    from .intelligence_agent import fetch_latest_threats
    threats = fetch_latest_threats(limit=5)
    if not threats:
        return "No new security reports found."
    
    lines = []
    for t in threats:
        lines.append(f"- [{t['source']}] {t['title']}: {t['link']}")
    return "\n".join(lines)


def get_db_stats():
    """Returns a summary of messages currently in the database."""
    from .models import Message
    from django.db.models import Count
    stats = Message.objects.values('source').annotate(count=Count('id'))
    if not stats:
        return "Database is empty."
    
    lines = ["Current Database Stats:"]
    for s in stats:
        lines.append(f"- {s['source']}: {s['count']} messages")
    return "\n".join(lines)


# ==========================================
# TOOL DEFINITIONS FOR GROQ
# ==========================================

from .insta_fetcher import check_insta_status, send_instagram_dm

AVAILABLE_TOOLS = {
    "get_recent_summary": get_recent_summary,
    "delete_all_spam": delete_all_spam,
    "add_favourite": add_favourite,
    "create_reminder": create_reminder,
    "send_whatsapp_message": send_whatsapp_message,
    "send_instagram_dm": send_instagram_dm,
    "check_insta_status": check_insta_status,
    "search_messages": search_messages,
    "get_all_senders": get_all_senders,
    "get_db_stats": get_db_stats,
    "get_latest_news": get_latest_news
}

groq_tools = [
    {
        "type": "function",
        "function": {
            "name": "get_recent_summary",
            "description": "Fetch a summary of recent messages (last 3 Days) and upcoming reminders. Always call this if the user asks 'what happened today', 'summarize my messages', etc."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_all_spam",
            "description": "Delete all messages from the database that are currently categorized as SPAM."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_favourite",
            "description": "Add a username to the Favourites list so their text messages bypass AI classification.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "The exact username/email to add."
                    },
                    "source": {
                        "type": "string",
                        "enum": ["gmail", "instagram", "whatsapp"],
                        "description": "Platform the user is on."
                    }
                },
                "required": ["username"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Create a new scheduled reminder/deadline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short title of the reminder."
                    },
                    "description": {
                        "type": "string",
                        "description": "Longer description of the reminder."
                    },
                    "raw_time": {
                        "type": "string",
                        "description": "ISO 8601 formatted datetime string indicating when the reminder should trigger."
                    }
                },
                "required": ["title", "description", "raw_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp_message",
            "description": "Send a WhatsApp message to a group or contact. Only use this if the user explicitly asks to send or reply with specific content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Group name or WhatsApp JID or Phone number."
                    },
                    "message": {
                        "type": "string",
                        "description": "The text content of the message."
                    }
                },
                "required": ["target", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_messages",
            "description": "Search the database for messages. Use 'sender' to filter by person name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sender": {"type": "string", "description": "Person name (e.g. Gaurav, Kriti)"},
                    "query": {"type": "string", "description": "Search keyword"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_db_stats",
            "description": "Get overall database statistics (message counts per source) to verify if data is synced."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_senders",
            "description": "Get a list of all unique senders in the system to help identify the correct name/handle."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_latest_news",
            "description": "Fetch current OSINT security threats and news.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_instagram_dm",
            "description": "Send a DM to an Instagram user on behalf of the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "Instagram username (e.g. kritisaw54)"},
                    "message": {"type": "string", "description": "Text message to send"}
                },
                "required": ["username", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_insta_status",
            "description": "Check if Instagram login/session is working. Use this to diagnose why Instagram messages are missing."
        }
    }
]


# ==========================================
# AGENT RUNTIME
# ==========================================

def _parse_raw_function_calls(text):
    """
    Fallback parser: Llama models sometimes output raw function tags
    instead of using Groq's tool-calling API. This parses multiple formats:
    - <function=search_messages({"sender": "Kriti"})></function>
    - <function=search_messages=[{"sender": "Kriti"}]></function>
    - <function=search_messages {"sender": "Kriti"}>
    """
    import re
    results = []
    
    # Pattern 1: <function=name ... args ...>
    # Flexible matching for name, connectors (=, (, space), and args ({ or [)
    pattern = r'<function=(\w+)\s*[=(]?\s*([\[\{].*?[\]\}])\s*\)?\s*>(?:</function>)?'
    matches = re.findall(pattern, text, re.DOTALL)
    
    for func_name, args_str in matches:
        try:
            # Clean up potential escapes or double-wrapped quotes
            clean_args = args_str.replace('\\"', '"')
            args = json.loads(clean_args)
            
            # If the model wrapped the dict in a list [{}], take the first item
            if isinstance(args, list) and len(args) > 0 and isinstance(args[0], dict):
                args = args[0]
            elif not isinstance(args, dict):
                args = {}
                
            results.append((func_name, args))
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to parse fallback args: {args_str} | Error: {e}")
            continue
    
    # Pattern 2: <function=name> (no args)
    if not results:
        no_args = re.findall(r'<function=(\w+)\s*/?>', text)
        for func_name in no_args:
            results.append((func_name, {}))
    
    # Pattern 3: <function>name</function>
    if not results:
        simple = re.findall(r'<function>(\w+)</function>', text)
        for func_name in simple:
            results.append((func_name, {}))
    
    # Pattern 4: Tool calling error extraction
    if not results:
        # Match pattern from Groq error strings: tool 'name={...}'
        tool_err = re.findall(r"tool '(\w+)\s*=\s*([\[\{].*?[\]\}])'", text)
        for func_name, args_str in tool_err:
            try:
                args = json.loads(args_str)
                if isinstance(args, list) and len(args) > 0:
                    args = args[0]
                results.append((func_name, args))
            except json.JSONDecodeError:
                continue
    
    return results



def ask_assistant(user_query):
    """
    Takes a natural language query and uses Groq to answer it.
    Can execute tools/functions. Includes fallback for raw function tag parsing.
    """
    if not getattr(settings, 'GROQ_API_KEY_CHAT', None):
        return "GROQ_API_KEY_CHAT is not configured. Assistant cannot reply."
        
    client = Groq(api_key=settings.GROQ_API_KEY_CHAT)
    
    now_str = timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z")
    
    messages = [
        {
            "role": "system", 
            "content": f"You are MailShield AI, the dedicated Personal Assistant for our user. Your goal is to manage their communication intelligence and security.\n"
                       f"Current Time: {now_str}\n"
                       f"PERSONA & STYLE:\n"
                       f"1. Tone: Warm, respectful, and highly proactive personal assistant. Use friendly Hinglish (Hindi + English).\n"
                       f"2. Be Observant: Don't just list data; tell the user WHY something matters. (e.g., 'Bhai, ye Prof ka mail urgent lag raha hai').\n"
                       f"3. Proactive Help: If a message asks for something, offer to draft a reply or create a reminder.\n"
                       f"4. Structure: When giving updates, explain one-by-one in an organized way.\n"
                       f"5. Address the user as 'Sir' or 'Bhai' (as per the vibe).\n\n"
                       f"TOOL RULES:\n"
                       f"- To find messages, use search_messages.\n"
                       f"- To check status/senders, use get_all_senders or get_db_stats.\n"
                       f"- To send messages, use send_whatsapp_message or send_instagram_dm.\n"
                       f"- NEVER hallucinate information. If you don't know, use a tool or say so."
        },
        {"role": "user", "content": user_query}
    ]

    try:
        # First API call
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=groq_tools,
            tool_choice="auto",
            max_tokens=1024
        )
        
        response_message = response.choices[0].message
        
        # === PATH 1: Proper tool calls via API ===
        if response_message.tool_calls:
            messages.append(response_message)
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_to_call = AVAILABLE_TOOLS.get(function_name)
                
                if function_to_call:
                    kwargs = {}
                    if tool_call.function.arguments:
                        parsed = json.loads(tool_call.function.arguments)
                        if isinstance(parsed, dict):
                            kwargs = parsed
                    
                    # Remove empty string values that confuse tools
                    kwargs = {k: v for k, v in kwargs.items() if v != "" and v is not None}
                        
                    logger.info(f"Agent executing tool: {function_name}({kwargs})")
                    try:
                        function_result = function_to_call(**kwargs)
                    except Exception as e:
                        function_result = f"Error executing tool: {e}"
                        
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": str(function_result),
                    })
                else:
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": f"Error: Tool '{function_name}' not found.",
                    })
                    
            # Second API call for final response
            second_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=1024
            )
            return second_response.choices[0].message.content.strip()

        # === PATH 2: Fallback — model hallucinated raw <function> tags ===
        content = response_message.content or ""
        raw_calls = _parse_raw_function_calls(content)
        
        if raw_calls:
            logger.warning(f"Fallback parser caught {len(raw_calls)} raw function call(s) in text.")
            tool_results = []
            
            for func_name, kwargs in raw_calls:
                function_to_call = AVAILABLE_TOOLS.get(func_name)
                if function_to_call:
                    kwargs = {k: v for k, v in kwargs.items() if v != "" and v is not None}
                    logger.info(f"Fallback executing: {func_name}({kwargs})")
                    try:
                        result = function_to_call(**kwargs)
                    except Exception as e:
                        result = f"Error: {e}"
                    tool_results.append(f"[{func_name}] Result:\n{result}")
                else:
                    tool_results.append(f"[{func_name}] Error: Tool not found.")
            
            # Feed results back to model for a human-friendly summary
            combined_results = "\n\n".join(tool_results)
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user", 
                "content": f"Tool results are below. Summarize them in Hinglish for the user:\n\n{combined_results}"
            })
            
            summary_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=1024
            )
            return summary_response.choices[0].message.content.strip()

        # === PATH 3: No tools needed, plain text response ===
        return content.strip()

    except Exception as e:
        error_str = str(e)
        logger.error(f"Chat agent error: {error_str}")
        
        # === PATH 4: Groq rejected a malformed tool call — recover ===
        if 'tool_use_failed' in error_str or 'failed_generation' in error_str:
            logger.warning("Groq tool_use_failed — attempting recovery from failed_generation.")
            
            # Extract the failed_generation text from the error
            raw_calls = _parse_raw_function_calls(error_str)
            
            if raw_calls:
                tool_results = []
                for func_name, kwargs in raw_calls:
                    function_to_call = AVAILABLE_TOOLS.get(func_name)
                    if function_to_call:
                        kwargs = {k: v for k, v in kwargs.items() if v != "" and v is not None}
                        logger.info(f"Recovery executing: {func_name}({kwargs})")
                        try:
                            result = function_to_call(**kwargs)
                        except Exception as tool_err:
                            result = f"Error: {tool_err}"
                        tool_results.append(f"[{func_name}] Result:\n{result}")
                    else:
                        tool_results.append(f"[{func_name}] Error: Tool not found.")
                
                # Feed results back to model for a clean summary
                combined_results = "\n\n".join(tool_results)
                try:
                    recovery_client = Groq(api_key=settings.GROQ_API_KEY_CHAT)
                    recovery_response = recovery_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": "You are MailShield AI. Summarize these tool results in friendly Hinglish. Be concise."},
                            {"role": "user", "content": f"User asked: {user_query}\n\nTool results:\n{combined_results}"}
                        ],
                        max_tokens=512
                    )
                    return recovery_response.choices[0].message.content.strip()
                except Exception as recovery_err:
                    logger.error(f"Recovery summary failed: {recovery_err}")
                    # Return raw results if summary fails
                    return "\n".join(tool_results)
        
        return f"Error communicating with AI Assistant: {error_str}"
