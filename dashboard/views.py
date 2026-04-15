from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Count, Q
from analyzer.models import Message, FavouriteUser, Reminder
from django.contrib import messages
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from analyzer.chat_agent import ask_assistant
from analyzer.reply_drafter import draft_reply
from analyzer.intelligence_agent import fetch_latest_threats


@login_required
def index(request):
    """
    FIX 8: Dashboard requires authentication via @login_required.
    FIX 12: Server-side pagination (25 messages per page).
    Enhanced with analytics data for the dashboard UI overhaul.
    """
    messages_qs = Message.objects.all().order_by('-received_at')

    # Allow filtering by category via GET params
    category = request.GET.get('category')
    if category:
        messages_qs = messages_qs.filter(category=category)

    phishing = request.GET.get('phishing')
    if phishing:
        messages_qs = messages_qs.filter(is_phishing=True)

    # FIX 12: Paginate results — 25 per page
    paginator = Paginator(messages_qs.prefetch_related('url_scans'), 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    favourite_users = FavouriteUser.objects.all().order_by('-created_at')
    reminders = Reminder.objects.filter(is_sent=False, remind_at__gte=timezone.now()).order_by('remind_at')[:10]

    # --- Analytics data for dashboard stats ---
    all_messages = Message.objects.all()
    total_count = all_messages.count()
    phishing_count = all_messages.filter(is_phishing=True).count()
    important_count = all_messages.filter(category='IMPORTANT').count()
    spam_count = all_messages.filter(category='SPAM').count()
    threat_count = all_messages.filter(category='THREAT').count()
    pending_reminders = Reminder.objects.filter(is_sent=False, remind_at__gte=timezone.now()).count()

    # Messages per source
    source_stats = dict(
        all_messages.values_list('source').annotate(count=Count('id')).values_list('source', 'count')
    )

    # Messages per category (for chart)
    category_stats = list(
        all_messages.values('category').annotate(count=Count('id')).order_by('-count')[:10]
    )

    # URLs scanned stats
    urls_scanned_count = all_messages.filter(urls_scanned=True).count()
    dangerous_urls = 0
    try:
        from analyzer.models import URLScan
        dangerous_urls = URLScan.objects.filter(is_safe=False).count()
    except Exception:
        pass

    # OSINT Threat Intel cache (briefly for performance)
    threat_intel = fetch_latest_threats(limit=5)

    context = {
        'page_obj': page_obj,
        'selected_category': category,
        'phishing': phishing,
        'favourite_users': favourite_users,
        'reminders': reminders,
        # Analytics
        'total_count': total_count,
        'phishing_count': phishing_count,
        'important_count': important_count,
        'spam_count': spam_count,
        'threat_count': threat_count,
        'pending_reminders': pending_reminders,
        'source_stats': source_stats,
        'category_stats': category_stats,
        'urls_scanned_count': urls_scanned_count,
        'dangerous_urls': dangerous_urls,
        'threat_intel': threat_intel,
    }
    return render(request, 'dashboard/index.html', context)


@login_required
def add_favourite(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        source = request.POST.get('source', 'instagram')
        if username:
            username = username.strip()
            if not FavouriteUser.objects.filter(username=username).exists():
                FavouriteUser.objects.create(username=username, source=source)
                messages.success(request, f"Added {username} to favourites.")
            else:
                messages.warning(request, f"{username} is already in favourites.")
    return redirect('dashboard-index')


@login_required
def remove_favourite(request, user_id):
    if request.method == 'POST':
        fav = get_object_or_404(FavouriteUser, id=user_id)
        username = fav.username
        fav.delete()
        messages.success(request, f"Removed {username} from favourites.")
    return redirect('dashboard-index')

@login_required
@csrf_exempt
def chat_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            query = data.get('message', '')
            if not query:
                return JsonResponse({'error': 'No message provided'}, status=400)
                
            reply = ask_assistant(query)
            return JsonResponse({'reply': reply})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
@csrf_exempt
def draft_reply_api(request):
    """API endpoint to generate an AI-drafted reply for a message."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            message_id = data.get('message_id')
            if not message_id:
                return JsonResponse({'error': 'No message_id provided'}, status=400)

            msg_obj = get_object_or_404(Message, id=message_id)
            reply_text = draft_reply(msg_obj)
            return JsonResponse({'reply': reply_text, 'category': msg_obj.category})
        except Message.DoesNotExist:
            return JsonResponse({'error': 'Message not found'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)
