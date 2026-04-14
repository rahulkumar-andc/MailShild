from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.utils import timezone
from analyzer.models import Message, FavouriteUser, Reminder
from django.contrib import messages
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from analyzer.chat_agent import ask_assistant
@login_required
def index(request):
    """
    FIX 8: Dashboard requires authentication via @login_required.
    FIX 12: Server-side pagination (25 messages per page).
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
    paginator = Paginator(messages_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    favourite_users = FavouriteUser.objects.all().order_by('-created_at')
    reminders = Reminder.objects.filter(is_sent=False, remind_at__gte=timezone.now()).order_by('remind_at')[:10]

    context = {
        'page_obj': page_obj,
        'selected_category': category,
        'phishing': phishing,
        'favourite_users': favourite_users,
        'reminders': reminders,
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
