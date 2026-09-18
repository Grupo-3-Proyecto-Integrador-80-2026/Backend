from django.shortcuts import render
from django.http import JsonResponse 
from .models import User

def health_check(request): 
    return JsonResponse({"status": "ok"})

def db_test(request): 
    user = User.objects.first()
    if user:
        return JsonResponse({ "message": f"Hola, trayendo usuario de la BD... encontrado: {user.username}" })
    return JsonResponse({ "message": "Hola, conectado a la BD, pero no hay usuarios todavía." })