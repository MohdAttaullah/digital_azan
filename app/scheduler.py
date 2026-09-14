"""Durable scheduler public name; constructor accepts AppConfig and injected services.

The legacy check_due_prayer API is retired: a returned prayer name alone cannot
provide transactional claims and a complete playback lifecycle.
"""
from app.controller import Controller

PrayerScheduler = Controller
