from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from analyzer.models import Message


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

    context = {
        'messages': page_obj,
        'page_obj': page_obj,
        'selected_category': category,
        'phishing': phishing,
    }
    return render(request, 'dashboard/index.html', context)
