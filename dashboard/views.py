from django.shortcuts import render
from analyzer.models import Message

def index(request):
    # Fetch all messages ordered by received_at descending
    messages = Message.objects.all().order_by('-received_at')
    
    # Allow filtering by category via GET params
    category = request.GET.get('category')
    if category:
        messages = messages.filter(category=category)
        
    context = {
        'messages': messages,
        'selected_category': category
    }
    return render(request, 'dashboard/index.html', context)
