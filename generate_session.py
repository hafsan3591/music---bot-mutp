"""
নিজের কম্পিউটারে বা Render-এর 'Shell' ট্যাবে চালাও:
    python3 generate_session.py

ফোন নম্বর + OTP দাও, যে স্ট্রিং পাবে সেটাই STRING_SESSION।
একটি আলাদা Telegram অ্যাকাউন্ট ব্যবহার করো, নিজের ব্যক্তিগত অ্যাকাউন্ট নয়।
"""

from pyrogram import Client

API_ID = int(input("API_ID দাও: "))
API_HASH = input("API_HASH দাও: ")

with Client(name="assistant_session", api_id=API_ID, api_hash=API_HASH, in_memory=True) as app:
    print("\n\n✅ এই যে তোমার STRING_SESSION, এটি Render-এর env-এ দাও:\n")
    print(app.export_session_string())
    print("\n\n")