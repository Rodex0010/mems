import os
import tempfile
import time
import sqlite3
import asyncio
import json
import traceback
import re
import uuid
import subprocess
import hashlib
import random
import math
from typing import List, Optional
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps, ImageSequence
from telegram import Update, InputSticker, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler, CallbackQueryHandler)
from telegram.constants import StickerFormat, ChatAction
from rembg import remove
import moviepy.editor as mp
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
import numpy as np
from telegram import Update
from telegram.ext import Application
from telegram.request import HTTPXRequest
import inspect as _inspect

# ========== غلاف آمن حول InlineKeyboardButton (يدعم الألوان لو المكتبة تدعمها) ==========
# خاصية "style" (الألوان: primary/success/danger) اتضافت لمكتبة python-telegram-bot
# بداية من إصدار 22.7. لو عندك نسخة أقدم، الكود هيتجاهل الألوان تلقائياً بدل
# ما يكسر البوت بالكامل برسالة "unexpected keyword argument 'style'".
try:
    _IKB_SUPPORTS_STYLE = 'style' in _inspect.signature(InlineKeyboardButton.__init__).parameters
except Exception:
    _IKB_SUPPORTS_STYLE = False

if not _IKB_SUPPORTS_STYLE:
    print("⚠️ نسخة python-telegram-bot المثبتة أقدم من 22.7، فألوان الأزرار (style) هتتجاهل.")
    print("   لتفعيل الألوان: pip install --upgrade python-telegram-bot")

def IKB(*args, **kwargs):
    """غلاف حول InlineKeyboardButton بيتجاهل style تلقائياً لو المكتبة مش بتدعمها"""
    if not _IKB_SUPPORTS_STYLE:
        kwargs.pop("style", None)
    return InlineKeyboardButton(*args, **kwargs)

# ========== زر "نسخ الرابط" الحقيقي (بينسخ للحافظة فوراً من غير ما يفتح قايمة/رسالة جديدة) ==========
# تليجرام ضاف خاصية copy_text لأزرار الكيبورد (Bot API 7.6 تقريباً)، لما المستخدم
# يدوس على الزر ده تليجرام بينسخ النص المحدد للحافظة على طول من غير ما يفتح أي حاجة.
# لو نسخة المكتبة المثبتة أقدم ومش بتدعمها، بنرجع للسلوك القديم (زر بيفتح رسالة
# فيها الرابط) عشان البوت يفضل شغال.
try:
    from telegram import CopyTextButton
except ImportError:
    CopyTextButton = None

try:
    _IKB_SUPPORTS_COPY_TEXT = CopyTextButton is not None and 'copy_text' in _inspect.signature(InlineKeyboardButton.__init__).parameters
except Exception:
    _IKB_SUPPORTS_COPY_TEXT = False

if not _IKB_SUPPORTS_COPY_TEXT:
    print("⚠️ نسخة python-telegram-bot المثبتة مش بتدعم زر نسخ الحافظة (copy_text).")
    print("   لتفعيل نسخ الرابط المباشر للحافظة: pip install --upgrade python-telegram-bot")

def copy_link_ikb(set_name: str, text: str = "📋 نسخ الرابط", style: str = "primary"):
    """زرار بينسخ رابط الاستيكر للحافظة مباشرة عند الضغط عليه (من غير فتح قايمة/رسالة جديدة)"""
    link = f"https://t.me/addstickers/{set_name}"
    if _IKB_SUPPORTS_COPY_TEXT:
        kwargs = {"copy_text": CopyTextButton(text=link)}
        if _IKB_SUPPORTS_STYLE:
            kwargs["style"] = style
        return InlineKeyboardButton(text, **kwargs)
    # المكتبة قديمة ومش بتدعم النسخ المباشر -> نرجع للسلوك القديم كحل بديل
    return IKB(text, callback_data=f"copy_{set_name}", style=style)

# ================== CONFIG ==================
BOT_TOKEN   = "8578887711:AAGhU7EueXA2-GjEp5IDY4me4tr1-j5rnAo"
CHANNEL_ID  = "@l_zor_l"
OWNER_USER  = "XCODE000"
BOT_USERNAME = "LOFEY18_bot"
ADMIN_IDS = [6210897462, 7876741744]  # أضف هنا ID المسؤولين

# ================== نظام الاشتراك المدفوع ==================
SUBSCRIPTION_ENABLED = False
SUBSCRIPTION_PLANS = {
    "monthly": {"price": 5, "days": 30, "name": {"ar": "شهري", "en": "Monthly"}},
    "quarterly": {"price": 12, "days": 90, "name": {"ar": "ربع سنوي", "en": "Quarterly"}},
    "yearly": {"price": 45, "days": 365, "name": {"ar": "سنوي", "en": "Yearly"}},
    "lifetime": {"price": 100, "days": 36500, "name": {"ar": "مدى الحياة", "en": "Lifetime"}}
}

# رابط الدفع (يمكنك تغييره لرابط باي بال أو ستريب)
PAYMENT_URL = "https://t.me/XCODE000"  # رابط الدفع عبر المطور

CUSTOM_EMOJIS = [
    "😎","🔥","💎","✨","⚡️","🌟","🎯","💡","🕶️","🤍",
    "🌈","💥","🌙","🌸","🌺","🌼","🍂","🍁","❄️","☀️",
    "🍀","🎨","🎭","🎪","🎤","🎧","🎮","🎲","🧩","🎵",
    "🎶","🎼","🎹","🎻","🎺","🎷","🥁","🎸","🪕","🎰",
    "🚀","✈️","🛸","🛰️","🗽","🗼","🎡","🎢","🎠","🏰"
]

LANGS = {
    "ar": {
        "start":"🎨 اختر نوع المحتوى:",
        "send_text":"📝 أرسل النص الآن:",
        "choose_style":"🎨 اختر الأسلوب:",
        "choose_effect":"✨ اختر التأثير (يمكن اختيار أكثر من واحد):",
        "choose_multiple_effects":"🔮 اختر التأثيرات الإضافية:",
        "choose_color":"🎨 اختر اللون:",
        "choose_color_dual_first":"اختر اللون الأول:",
        "choose_color_dual_second":"تمام، دلوقتى اختر اللون التاني:",
        "color_dual":"🎨🎨 لون مشترك",
        "choose_sticker_type":"🏷 اختر نوع الاستيكر:",
        "sticker_type_custom_emoji":"⭐ إيموجي مميز",
        "sticker_type_regular":"😊 إيموجي عادي",
        "choose_emoji":"😊 اختر الإيموجى:",
        "choose_font":"🔤 اختر الخط:",
        "generating":"⚡️ جارى التصميم...",
        "done":"✅ تم رفع ملصق التوثيق:",
        "error":"❌ خطأ:",
        "member":"📢 اشترك بالقناة أولاً:\n@l_zor_l",
        "check":"✅ تحقق من الاشتراك",
        "developer":"💬 المطور",
        "text":"⭐️ أرسل النص ",
        "photo":"⭐️ أرسل الصور ",
        "video":"⭐️ أرسل فيديو",
        "animated":"⭐️ استيكر متحرك",
        "regular_sticker":"🎭 استيكر عادى",
        "regular_sticker_desc":"⭐️ أرسل الصور ، فيديو قصير، أو GIF لتحويله إلى استيكر تلجرام عادى (غير مميز)",
        "regular_sticker_processing":"⚡️ جارى إنشاء الاستيكر العادى...",
        "regular_sticker_invalid":"❌ يرجى إرسال صورة أو فيديو أو GIF صالح",
        "sticker_to_emoji":"⭐️ استيكر لإيموجي",
        "my_stickers":"📁 استيكراتي",
        "lang":"🌐 تغيير اللغة",
        "style_3d":"🏗️ 3D مبنى",
        "style_3d_gold":"🌟 3D ذهبى",
        "style_cartoon":"🎭 كرتونى ملون",
        "style_arabic":"🕌 خط عربى فخم",
        "style_metal":"🔩 معدنى",
        "style_neon":"💡 نيون ملون",
        "style_gradient":"🌈 تدرج ألوان",
        "style_3d_building":"🏛️ 3D مبني",
        "style_3d_metal":"🏢 3D معادن",
        "style_3d_crystal":"💎 3D كريستال",
        "style_3d_glass":"🔮 3D زجاج",
        "style_arabic_calligraphy":"🎨 خط عربي مزخرف",
        "style_english_fancy":"✨ زخرفة إنجليزية",
        "style_arabic_pattern":"🌺 زخارف عربية",
        "style_english_pattern":"🎭 زخارف إنجليزية",
        "effect_shadow":"🌑 ظل",
        "effect_glow":"✨ إضاءة",
        "effect_reflection":"💧 انعكاس",
        "effect_frame":"🖼 إطار",
        "effect_neon":"💡 نيون",
        "effect_gradient":"🌈 تدرج لونى",
        "effect_3d_bevel":"🔶 إنحناء 3D",
        "effect_blur":"🌫 ضبابى",
        "effect_sparkle":"💫 تلميع",
        "effect_rainbow":"🌈 قوس قزح",
        "effect_border":"🔲 حدود",
        "effect_outline":"📐 تحديد",
        "effect_metalic":"🔩 معدنى",
        "effect_water":"💧 مائى",
        "effect_fire":"🔥 نارى",
        "effect_ice":"❄️ جليدى",
        "effect_3d_depth":"🏗️ عمق 3D",
        "effect_reflection_water":"💦 انعكاس مائي",
        "effect_3d_shadow":"🌑 ظل 3D",
        "effect_glossy":"✨ لامع",
        "effect_arabic_ornament":"🌺 زخرفة عربية",
        "effect_english_ornament":"🎭 زخرفة إنجليزية",
        "effect_gold_leaf":"🌟 ورق ذهبي",
        "effect_silver_leaf":"💿 ورق فضي",
        "effect_crystal_shine":"💎 بريق كريستال",
        "effect_diamond_cut":"💎 قطع ماسي",
        "effect_royal_frame":"👑 إطار ملكي",
        "effect_luxury_border":"💎 حدود فاخرة",
        "color_gold":"🌟 ذهبى",
        "color_silver":"💿 فضى",
        "color_red":"🔴 أحمر",
        "color_blue":"🔵 أزرق",
        "color_green":"🟢 أخضر",
        "color_purple":"🟣 بنفسجى",
        "color_black":"⚫ أسود",
        "color_white":"⚪ أبيض",
        "color_pink":"🌸 وردى",
        "color_cyan":"💎 سيان",
        "color_orange":"🍊 برتقالى",
        "color_yellow":"🌻 أصفر",
        "color_brown":"🍫 بنى",
        "color_teal":"🦢 تركواز",
        "color_lavender":"💜 لافندر",
        "color_maroon":"🍷 كستنائى",
        "color_navy":"🌌 بحرى",
        "color_olive":"🫒 زيتونى",
        "color_coral":"🐚 مرجانى",
        "font_arial":"Arial عادى",
        "font_bold":"Arial غامق",
        "font_times":"Times New Roman",
        "font_courier":"Courier New",
        "font_impact":"Impact كبير",
        "font_comic":"Comic Sans",
        "font_arabic":"🕌 خط عربى",
        "font_fancy":"💎 خط فاخر",
        "font_script":"✍️ خط يدوى",
        "font_3d":"🏗️ خط 3D",
        "font_rounded":"🔵 خط دائرى",
        "font_graffiti":"🎨 جرافيتى",
        "font_old":"🏺 خط قديم",
        "font_modern":"🚀 خط حديث",
        "font_arabic_thuluth":"🌙 خط الثلث",
        "font_arabic_naskh":"📖 خط النسخ",
        "font_arabic_diwani":"🎨 خط الديواني",
        "font_arabic_ruqaa":"✍️ خط الرقعة",
        "font_english_gothic":"🏰 خط قوطي",
        "font_english_cursive":"🖋️ خط إنجليزي متصل",
        "font_english_modern":"🚀 خط إنجليزي حديث",
        "subscribe":"⭐ اشترك الآن",
        "subscribe_title":"💰 اختر خطة الاشتراك:",
        "plan_monthly":"📅 شهرى – 5$",
        "plan_quarterly":"📊 ربع سنوى – 12$",
        "plan_yearly":"🎉 سنوى – 45$",
        "plan_lifetime":"👑 مدى الحياة – 100$",
        "sub_activated":"✅ تم تفعيل الاشتراك بنجاح!",
        "sub_disabled":"الاشتراك المدفوع معطل حالياً.",
        "multi_effect":"🔮 تأثيرات إضافية",
        "add_more_effects":"✨ أضف تأثيرات أكثر",
        "finish_effects":"✅ إنهاء اختيار التأثيرات",
        "back":"🔙 رجوع",
        "animated_desc":"🎬 أرسل ملف GIF أو فيديو قصير لتحويله إلى استيكر متحرك",
        "max_anim_length":"⏰ أقصى مدة: 3 ثواني",
        "processing_anim":"⚡️ جاري معالجة الاستيكر المتحرك...",
        "anim_success":"✅ تم إنشاء الاستيكر المتحرك بنجاح!",
        "anim_error":"❌ خطأ في معالجة الاستيكر المتحرك",
        "file_too_large":"📁 الملف كبير جداً (الحد الأقصى 256KB)",
        "invalid_gif":"❌ ملف GIF غير صالح",
        "duration_too_long":"⏰ المدة طويلة جداً (الحد الأقصى 3 ثواني)",
        "admin_menu":"🔧 قائمة الأدمن",
        "toggle_subscription":"🔀 تفعيل/تعطيل الاشتراك",
        "subscription_management":"👑 إدارة الاشتراكات",
        "add_subscription":"➕ إضافة اشتراك",
        "remove_subscription":"➖ إزالة اشتراك",
        "view_subscribers":"👥 عرض المشتركين",
        "subscription_stats":"📊 إحصائيات الاشتراكات",
        "search_user":"🔍 بحث عن مستخدم",
        "enter_user_id":"📝 أرسل آيدي المستخدم:",
        "user_not_found":"❌ المستخدم غير موجود",
        "user_subscription_info":"📋 معلومات اشتراك المستخدم:",
        "expiry_date":"📅 تاريخ الانتهاء:",
        "days_remaining":"⏳ الأيام المتبقية:",
        "subscription_active":"✅ الاشتراك مفعل",
        "subscription_expired":"❌ الاشتراك منتهي",
        "choose_plan_for_user":"🎯 اختر الباقة للمستخدم:",
        "subscription_added":"✅ تم إضافة الاشتراك بنجاح",
        "subscription_removed":"✅ تم إزالة الاشتراك بنجاح",
        "all_subscribers":"👥 جميع المشتركين ({count})",
        "no_subscribers":"❌ لا يوجد مشتركين حالياً",
        "subscriber_item":"👤 {username} - {plan} - {days} يوم",
        "stats_total":"📈 الإجمالي: {total}",
        "stats_by_plan":"📊 حسب الباقة:",
        "stats_expiring_soon":"⚠️ تنتهي قريباً: {count}",
        "user_id_invalid":"❌ آيدي المستخدم غير صالح",
        "go_back_admin":"🔙 رجوع للأدمن",
        "stats":"📊 إحصائيات البوت",
        "broadcast":"📢 إرسال إشعار لجميع المستخدمين",
        "user_stats":"👥 عدد المستخدمين: {count}",
        "premium_stats":"⭐ عدد المشتركين: {count}",
        "broadcast_sent":"✅ تم إرسال الإشعار لـ {count} مستخدم",
        "enter_broadcast":"⭐️ أرسل النص  الإشعار الآن:",
        "cancel":"🚫 إلغاء",
        "my_stickers_title":"📁 استيكراتي السابقة:",
        "no_stickers":"❌ لم تقم بإنشاء أي استيكر بعد!",
        "open_link":"🔗 افتح الرابط",
        "copy_link":"📋 انسخ الرابط",
        "recent_stickers":"🕒 آخر الاستيكرات",
        "all_stickers":"📂 جميع الاستيكرات",
        "processing_video_with_text":"🎬 جاري إضافة النص وتجهيز الفيديو...",
        "text_style_choice":"📝 اختر ترتيب النص:",
        "style_one_line":"📏 سطر واحد",
        "style_two_lines":"📐 سطرين تحت بعض",
        "remove_bg_choice":"🎭 اختر إزالة الخلفية:",
        "remove_bg_yes":"✅ نعم، أزل الخلفية",
        "remove_bg_no":"❌ لا، أبق الخلفية كما هي",
        "processing_photo":"🖼 جاري معالجة الصورة...",
        "sticker_processing":"🎭 جاري تحويل الاستيكر إلى رمزية مميزة...",
        "compressing_file":"📦 جاري ضغط الملف...",
        "conversion_success":"✅ تم التحويل إلى رمزية مميزة بنجاح!",
        "conversion_failed":"❌ فشل في التحويل، جاري المحاولة كاستيكر عادي...",
        "file_too_big_after_compression":"⚠️ الملف كبير جداً حتى بعد الضغط",
        "max_emoji_size":"📊 الحد الأقصى لرمزية مميزة: 256KB",
        "max_sticker_size":"📊 الحد الأقصى للاستيكر العادي: 512KB",
        "gif_conversion":"🎬 جاري تحويل GIF إلى رمزية مميزة...",
        "converting_to_webm":"🔄 جاري تحويل إلى WebM...",
        "webm_conversion_failed":"⚠️ فشل التحويل إلى WebM، جاري المحاولة بصيغة أخرى...",
        "video_too_long":"⏰ الفيديو طويل جداً، جاري قصه إلى 3 ثواني...",
        "optimizing_video":"🎬 جاري تحسين الفيديو للرمزية المميزة..."
    },
    "en": {
        "start":"🎨 Choose content type:",
        "send_text":"📝 Send text now:",
        "choose_style":"🎨 Choose style:",
        "choose_effect":"✨ Choose effect (you can choose multiple):",
        "choose_multiple_effects":"🔮 Choose additional effects:",
        "choose_color":"🎨 Choose color:",
        "choose_color_dual_first":"Choose the first color:",
        "choose_color_dual_second":"Now choose the second color:",
        "color_dual":"🎨🎨 Split color",
        "choose_sticker_type":"🏷 Choose sticker type:",
        "sticker_type_custom_emoji":"⭐ Custom emoji",
        "sticker_type_regular":"😊 Regular sticker",
        "choose_emoji":"😊 Choose emoji:",
        "choose_font":"🔤 Choose font:",
        "generating":"⚡️ Generating...",
        "done":"✅ Verified emoji sticker uploaded:",
        "error":"❌ Error:",
        "member":"📢 Join the channel first:\n@l_zor_l",
        "check":"✅ Check subscription",
        "developer":"💬 Developer",
        "text":"📝 Send text",
        "photo":"🖼 Send photo",
        "video":"🎥 Send video",
        "animated":"✨ Animated sticker",
        "regular_sticker":"🎭 Regular Sticker",
        "regular_sticker_desc":"🖼 Send a photo, short video, or GIF to turn it into a regular (non-premium) Telegram sticker",
        "regular_sticker_processing":"⚡️ Creating regular sticker...",
        "regular_sticker_invalid":"❌ Please send a valid photo, video, or GIF",
        "sticker_to_emoji":"🎭 Sticker to Emoji",
        "my_stickers":"📁 My Stickers",
        "lang":"🌐 Change language",
        "style_3d":"🏗️ 3D Building",
        "style_3d_gold":"🌟 3D Gold",
        "style_cartoon":"🎭 Cartoon Color",
        "style_arabic":"🕌 Arabic Fancy",
        "style_metal":"🔩 Metal",
        "style_neon":"💡 Colorful Neon",
        "style_gradient":"🌈 Color Gradient",
        "style_3d_building":"🏛️ 3D Building",
        "style_3d_metal":"🏢 3D Metal",
        "style_3d_crystal":"💎 3D Crystal",
        "style_3d_glass":"🔮 3D Glass",
        "style_arabic_calligraphy":"🎨 Arabic Calligraphy",
        "style_english_fancy":"✨ English Fancy",
        "style_arabic_pattern":"🌺 Arabic Patterns",
        "style_english_pattern":"🎭 English Patterns",
        "effect_shadow":"🌑 Shadow",
        "effect_glow":"✨ Glow",
        "effect_reflection":"💧 Reflection",
        "effect_frame":"🖼 Frame",
        "effect_neon":"💡 Neon",
        "effect_gradient":"🌈 Gradient",
        "effect_3d_bevel":"🔶 3D Bevel",
        "effect_blur":"🌫 Blur",
        "effect_sparkle":"💫 Sparkle",
        "effect_rainbow":"🌈 Rainbow",
        "effect_border":"🔲 Border",
        "effect_outline":"📐 Outline",
        "effect_metalic":"🔩 Metalic",
        "effect_water":"💧 Water",
        "effect_fire":"🔥 Fire",
        "effect_ice":"❄️ Ice",
        "effect_3d_depth":"🏗️ 3D Depth",
        "effect_reflection_water":"💦 Water Reflection",
        "effect_3d_shadow":"🌑 3D Shadow",
        "effect_glossy":"✨ Glossy",
        "effect_arabic_ornament":"🌺 Arabic Ornament",
        "effect_english_ornament":"🎭 English Ornament",
        "effect_gold_leaf":"🌟 Gold Leaf",
        "effect_silver_leaf":"💿 Silver Leaf",
        "effect_crystal_shine":"💎 Crystal Shine",
        "effect_diamond_cut":"💎 Diamond Cut",
        "effect_royal_frame":"👑 Royal Frame",
        "effect_luxury_border":"💎 Luxury Border",
        "color_gold":"🌟 Gold",
        "color_silver":"💿 Silver",
        "color_red":"🔴 Red",
        "color_blue":"🔵 Blue",
        "color_green":"🟢 Green",
        "color_purple":"🟣 Purple",
        "color_black":"⚫ Black",
        "color_white":"⚪ White",
        "color_pink":"🌸 Pink",
        "color_cyan":"💎 Cyan",
        "color_orange":"🍊 Orange",
        "color_yellow":"🌻 Yellow",
        "color_brown":"🍫 Brown",
        "color_teal":"🦢 Teal",
        "color_lavender":"💜 Lavender",
        "color_maroon":"🍷 Maroon",
        "color_navy":"🌌 Navy",
        "color_olive":"🫒 Olive",
        "color_coral":"🐚 Coral",
        "font_arial":"Arial Regular",
        "font_bold":"Arial Bold",
        "font_times":"Times New Roman",
        "font_courier":"Courier New",
        "font_impact":"Impact Large",
        "font_comic":"Comic Sans",
        "font_arabic":"🕌 Arabic Font",
        "font_fancy":"💎 Fancy Font",
        "font_script":"✍️ Script Font",
        "font_3d":"🏗️ 3D Font",
        "font_rounded":"🔵 Rounded Font",
        "font_graffiti":"🎨 Graffiti Font",
        "font_old":"🏺 Old Font",
        "font_modern":"🚀 Modern Font",
        "font_arabic_thuluth":"🌙 Thuluth Font",
        "font_arabic_naskh":"📖 Naskh Font",
        "font_arabic_diwani":"🎨 Diwani Font",
        "font_arabic_ruqaa":"✍️ Ruqaa Font",
        "font_english_gothic":"🏰 Gothic Font",
        "font_english_cursive":"🖋️ Cursive Font",
        "font_english_modern":"🚀 Modern English Font",
        "subscribe":"⭐ Subscribe Now",
        "subscribe_title":"💰 Choose subscription plan:",
        "plan_monthly":"📅 Monthly – 5$",
        "plan_quarterly":"📊 Quarterly – 12$",
        "plan_yearly":"🎉 Yearly – 45$",
        "plan_lifetime":"👑 Lifetime – 100$",
        "sub_activated":"✅ Subscription activated successfully!",
        "sub_disabled":"Paid subscription is currently disabled.",
        "multi_effect":"🔮 More effects",
        "add_more_effects":"✨ Add more effects",
        "finish_effects":"✅ Finish selecting effects",
        "back":"🔙 Back",
        "animated_desc":"🎬 Send a GIF or short video to convert to animated sticker",
        "max_anim_length":"⏰ Max duration: 3 seconds",
        "processing_anim":"⚡️ Processing animated sticker...",
        "anim_success":"✅ Animated sticker created successfully!",
        "anim_error":"❌ Error processing animated sticker",
        "file_too_large":"📁 File too large (max 256KB)",
        "invalid_gif":"❌ Invalid GIF file",
        "duration_too_long":"⏰ Duration too long (max 3 seconds)",
        "admin_menu":"🔧 Admin Menu",
        "toggle_subscription":"🔀 Toggle Subscription",
        "subscription_management":"👑 Subscription Management",
        "add_subscription":"➕ Add Subscription",
        "remove_subscription":"➖ Remove Subscription",
        "view_subscribers":"👥 View Subscribers",
        "subscription_stats":"📊 Subscription Stats",
        "search_user":"🔍 Search User",
        "enter_user_id":"📝 Send user ID:",
        "user_not_found":"❌ User not found",
        "user_subscription_info":"📋 User subscription info:",
        "expiry_date":"📅 Expiry date:",
        "days_remaining":"⏳ Days remaining:",
        "subscription_active":"✅ Subscription active",
        "subscription_expired":"❌ Subscription expired",
        "choose_plan_for_user":"🎯 Choose plan for user:",
        "subscription_added":"✅ Subscription added successfully",
        "subscription_removed":"✅ Subscription removed successfully",
        "all_subscribers":"👥 All Subscribers ({count})",
        "no_subscribers":"❌ No subscribers currently",
        "subscriber_item":"👤 {username} - {plan} - {days} days",
        "stats_total":"📈 Total: {total}",
        "stats_by_plan":"📊 By plan:",
        "stats_expiring_soon":"⚠️ Expiring soon: {count}",
        "user_id_invalid":"❌ User ID invalid",
        "go_back_admin":"🔙 Back to Admin",
        "stats":"📊 Bot Statistics",
        "broadcast":"📢 Broadcast to all users",
        "user_stats":"👥 Total users: {count}",
        "premium_stats":"⭐ Premium users: {count}",
        "broadcast_sent":"✅ Broadcast sent to {count} users",
        "enter_broadcast":"📝 Send broadcast message now:",
        "cancel":"🚫 Cancel",
        "my_stickers_title":"📁 My Previous Stickers:",
        "no_stickers":"❌ You haven't created any stickers yet!",
        "open_link":"🔗 Open Link",
        "copy_link":"📋 Copy Link",
        "recent_stickers":"🕒 Recent Stickers",
        "all_stickers":"📂 All Stickers",
        "processing_video_with_text":"🎬 Adding text and processing video...",
        "text_style_choice":"📝 Choose text arrangement:",
        "style_one_line":"📏 One line",
        "style_two_lines":"📐 Two lines",
        "remove_bg_choice":"🎭 Choose background removal:",
        "remove_bg_yes":"✅ Yes, remove background",
        "remove_bg_no":"❌ No, keep background as is",
        "processing_photo":"🖼 Processing photo...",
        "sticker_processing":"🎭 Converting sticker to custom emoji...",
        "compressing_file":"📦 Compressing file...",
        "conversion_success":"✅ Successfully converted to custom emoji!",
        "conversion_failed":"❌ Conversion failed, trying as regular sticker...",
        "file_too_big_after_compression":"⚠️ File too big even after compression",
        "max_emoji_size":"📊 Max custom emoji size: 256KB",
        "max_sticker_size":"📊 Max regular sticker size: 512KB",
        "gif_conversion":"🎬 Converting GIF to custom emoji...",
        "converting_to_webm":"🔄 Converting to WebM...",
        "webm_conversion_failed":"⚠️ Failed to convert to WebM, trying another format...",
        "video_too_long":"⏰ Video too long, cropping to 3 seconds...",
        "optimizing_video":"🎬 Optimizing video for custom emoji..."
    }
}

USER_DATA = {}
TEXT_RECEIVED, STYLE_CHOICE, FONT_CHOICE, EFFECT_CHOICE, COLOR_CHOICE, EMOJI_CHOICE, BROADCAST_MODE, TEXT_ARRANGEMENT, REMOVE_BG_CHOICE, STICKER_TYPE_CHOICE = range(10)

# ========== DB & Subscriptions ==========
def init_db():
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, 
                  first_name TEXT, last_name TEXT, lang TEXT DEFAULT 'ar',
                  join_date INTEGER, expiry INTEGER DEFAULT 0)''')
    
    # إنشاء جدول لحفظ روابط الاستيكرات
    c.execute('''CREATE TABLE IF NOT EXISTS user_stickers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  sticker_set_name TEXT,
                  created_at INTEGER,
                  title TEXT,
                  is_custom_emoji BOOLEAN DEFAULT 0,
                  is_video BOOLEAN DEFAULT 0)''')
    
    # إنشاء جدول لتسجيل الاشتراكات
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  plan TEXT,
                  days INTEGER,
                  admin_id INTEGER,
                  added_date INTEGER)''')
    
    # إنشاء جدول لتتبع الاستخدام اليومي
    c.execute('''CREATE TABLE IF NOT EXISTS daily_usage
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  usage_date TEXT,
                  usage_count INTEGER DEFAULT 0)''')
    
    try:
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
    except:
        pass
    
    conn.commit()
    conn.close()

def is_premium(user_id: int) -> bool:
    if not SUBSCRIPTION_ENABLED: 
        return True
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT expiry FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0] > int(time.time()): 
        return True
    return False

def get_user_lang(user_id: int) -> str:
    """الحصول على لغة المستخدم"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "ar"

def update_user_lang(user_id: int, lang: str):
    """تحديث لغة المستخدم"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, lang) VALUES (?, ?)", (user_id, lang))
    c.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
    conn.commit()
    conn.close()

def save_sticker_link(user_id: int, sticker_set_name: str, title: str = "", is_custom_emoji: bool = False, is_video: bool = False):
    """حفظ رابط الاستيكر في قاعدة البيانات"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''INSERT INTO user_stickers 
                 (user_id, sticker_set_name, created_at, title, is_custom_emoji, is_video) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (user_id, sticker_set_name, int(time.time()), title, is_custom_emoji, is_video))
    conn.commit()
    conn.close()

def get_user_stickers(user_id: int, limit: int = 10):
    """الحصول على روابط استيكرات المستخدم"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''SELECT sticker_set_name, created_at, title, is_custom_emoji, is_video 
                 FROM user_stickers 
                 WHERE user_id=? 
                 ORDER BY created_at DESC 
                 LIMIT ?''', (user_id, limit))
    stickers = c.fetchall()
    conn.close()
    return stickers

def get_user_stats():
    """الحصول على إحصائيات المستخدمين"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    active_threshold = int(time.time()) - (30 * 86400)
    c.execute("SELECT COUNT(*) FROM users WHERE join_date > ?", (active_threshold,))
    active_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE expiry > ?", (int(time.time()),))
    premium_users = c.fetchone()[0]
    
    conn.close()
    
    return {
        "total": total_users,
        "active": active_users,
        "premium": premium_users
    }

def get_all_users():
    """الحصول على جميع مستخدمي البوت"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

def save_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """حفظ بيانات المستخدم"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    exists = c.fetchone()
    
    if not exists:
        c.execute('''INSERT INTO users 
                     (user_id, username, first_name, last_name, join_date, lang) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (user_id, username, first_name, last_name, int(time.time()), "ar"))
    else:
        c.execute('''UPDATE users SET 
                     username=?, first_name=?, last_name=?, join_date=?
                     WHERE user_id=?''',
                  (username, first_name, last_name, int(time.time()), user_id))
    
    conn.commit()
    conn.close()

def add_user_subscription(user_id: int, plan_key: str, admin_id: int = None):
    """إضافة اشتراك للمستخدم"""
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if not plan:
        return False
    
    expiry = int(time.time()) + (plan["days"] * 86400)
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    c.execute("INSERT OR REPLACE INTO users (user_id, expiry) VALUES (?, ?)", (user_id, expiry))
    c.execute("INSERT INTO subscriptions_log (user_id, plan, days, admin_id, added_date) VALUES (?, ?, ?, ?, ?)",
              (user_id, plan_key, plan["days"], admin_id, int(time.time())))
    
    conn.commit()
    conn.close()
    return True

def get_user_subscription_info(user_id: int):
    """الحصول على معلومات اشتراك المستخدم"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    c.execute("SELECT expiry FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    
    if not row or not row[0]:
        conn.close()
        return {"active": False, "expiry": None, "plan": None, "days_left": 0}
    
    expiry = row[0]
    current_time = int(time.time())
    
    if expiry > current_time:
        days_left = (expiry - current_time) // 86400
        
        # محاولة تخمين الباقة بناءً على المدة
        plan_name = "غير معروف"
        for plan_key, plan in SUBSCRIPTION_PLANS.items():
            if abs((expiry - current_time) - (plan["days"] * 86400)) < 86400 * 5:  # هامش 5 أيام
                plan_name = plan_key
                break
        
        result = {
            "active": True,
            "expiry": expiry,
            "plan": plan_name,
            "days_left": days_left,
            "expiry_date": time.strftime("%Y-%m-%d %H:%M", time.localtime(expiry))
        }
    else:
        result = {"active": False, "expiry": expiry, "plan": None, "days_left": 0}
    
    conn.close()
    return result

def get_all_subscribers():
    """الحصول على جميع المشتركين"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    c.execute("SELECT user_id, expiry FROM users WHERE expiry > ? ORDER BY expiry DESC", (int(time.time()),))
    subscribers = c.fetchall()
    
    conn.close()
    return subscribers

def remove_subscription(user_id: int):
    """إزالة اشتراك المستخدم"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    c.execute("UPDATE users SET expiry = 0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    
    return True

def get_subscription_stats():
    """إحصائيات الاشتراكات"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    current_time = int(time.time())
    
    # إجمالي المشتركين النشطين
    c.execute("SELECT COUNT(*) FROM users WHERE expiry > ?", (current_time,))
    active = c.fetchone()[0]
    
    # المشتركين حسب الباقة (تقريبي)
    stats = {"total_active": active, "plans": {}, "expiring_soon": 0}
    
    for plan_key in SUBSCRIPTION_PLANS:
        c.execute("SELECT COUNT(*) FROM subscriptions_log WHERE plan=?", (plan_key,))
        stats["plans"][plan_key] = c.fetchone()[0]
    
    # المشتركين الذين ينتهي اشتراكهم خلال 7 أيام
    week_later = current_time + (7 * 86400)
    c.execute("SELECT COUNT(*) FROM users WHERE expiry > ? AND expiry <= ?", (current_time, week_later))
    stats["expiring_soon"] = c.fetchone()[0]
    
    conn.close()
    return stats

# ========== نظام تتبع الاستخدام اليومي ==========
def check_and_update_usage(user_id: int, max_daily_usage: int = 3) -> bool:
    """التحقق من الاستخدام اليومي وتحديثه"""
    if not SUBSCRIPTION_ENABLED:
        return True
    
    # الأدمن يستخدمون بدون حدود
    if user_id in ADMIN_IDS:
        return True
    
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    today = time.strftime("%Y-%m-%d")
    
    # التحقق من حالة الاشتراك أولاً
    c.execute("SELECT expiry FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    
    if row and row[0] > int(time.time()):  # إذا كان مشتركاً
        conn.close()
        return True  # المشتركون يستخدمون بدون حدود
    
    # للمستخدمين العاديين
    c.execute('''SELECT usage_count FROM daily_usage 
                 WHERE user_id=? AND usage_date=?''', (user_id, today))
    row = c.fetchone()
    
    if not row:
        # أول استخدام اليوم
        c.execute('''INSERT INTO daily_usage (user_id, usage_date, usage_count)
                     VALUES (?, ?, 1)''', (user_id, today))
        conn.commit()
        conn.close()
        return True
    else:
        usage_count = row[0]
        if usage_count >= max_daily_usage:
            conn.close()
            return False  # تجاوز الحد اليومي
        
        # زيادة العداد
        c.execute('''UPDATE daily_usage SET usage_count = usage_count + 1
                     WHERE user_id=? AND usage_date=?''', (user_id, today))
        conn.commit()
        conn.close()
        return True

def get_today_usage(user_id: int) -> int:
    """الحصول على عدد مرات الاستخدام اليومي"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    today = time.strftime("%Y-%m-%d")
    c.execute('''SELECT usage_count FROM daily_usage 
                 WHERE user_id=? AND usage_date=?''', (user_id, today))
    row = c.fetchone()
    
    conn.close()
    return row[0] if row else 0

def reset_daily_usage():
    """إعادة تعيين الاستخدام اليومي (تشغيل يومي)"""
    conn = sqlite3.connect("users.db", check_same_thread=False)
    c = conn.cursor()
    
    yesterday = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400))
    c.execute("DELETE FROM daily_usage WHERE usage_date < ?", (yesterday,))
    
    conn.commit()
    conn.close()

# ========== Utilities ==========
COLOR_PALETTE = {
    "gold": (255, 215, 0), "silver": (192, 192, 192), "red": (255, 0, 0),
    "blue": (0, 0, 255), "green": (0, 255, 0), "purple": (128, 0, 128),
    "black": (0, 0, 0), "white": (255, 255, 255), "pink": (255, 192, 203),
    "cyan": (0, 255, 255), "orange": (255, 165, 0), "yellow": (255, 255, 0),
    "brown": (165, 42, 42), "teal": (0, 128, 128), "lavender": (230, 230, 250),
    "maroon": (128, 0, 0), "navy": (0, 0, 128), "olive": (128, 128, 0),
    "coral": (255, 127, 80)
}

def color_rgb(name: str):
    """
    يرجع لون واحد (r,g,b) عادي، أو - لو الاسم بصيغة 'dual:color1:color2' (اللون المشترك) -
    يرجع tuple فيه اللونين مع بعض عشان النص يترسم متقسم بينهم.
    """
    if isinstance(name, str) and name.startswith("dual:"):
        try:
            _, c1, c2 = name.split(":", 2)
            return (COLOR_PALETTE.get(c1, COLOR_PALETTE["gold"]), COLOR_PALETTE.get(c2, COLOR_PALETTE["silver"]))
        except Exception:
            pass
    return COLOR_PALETTE.get(name, (255, 215, 0))

def _solid_fill_color(fill):
    """
    بعض التأثيرات (زي التدرج/التظليل) محتاجة تعمل حسابات رياضية زي //2 أو ضرب
    على قيم r,g,b - وده بيبوظ لو اللون جاي 'لون مشترك' (dual) لأنه بيبقى
    tuple فيه لونين ((r1,g1,b1),(r2,g2,b2)) مش لون واحد (r,g,b)، فبيطلع
    الخطأ: unsupported operand type(s) for //: 'tuple' and 'int'.
    الدالة دي بترجع لون واحد صالح للحسابات دايماً: لو اللون مشترك بترجع
    أول لون من الاتنين كممثل، ولو عادي بترجعه زي ما هو من غير تعديل.
    """
    if isinstance(fill, tuple) and len(fill) == 2 and isinstance(fill[0], tuple):
        return fill[0]
    return fill

def build_color_palette_kb(lang: str, prefix: str = "color_", include_dual: bool = True, include_back: bool = True):
    """يبني كيبورد ألوان قابل لإعادة الاستخدام (لاختيار لون عادي أو أول/تاني لون فى اللون المشترك)"""
    rows = [
        [IKB(LANGS[lang]["color_gold"], callback_data=f"{prefix}gold", style="primary"),
         IKB(LANGS[lang]["color_silver"], callback_data=f"{prefix}silver", style="success"),
         IKB(LANGS[lang]["color_red"], callback_data=f"{prefix}red", style="primary")],
        [IKB(LANGS[lang]["color_blue"], callback_data=f"{prefix}blue", style="success"),
         IKB(LANGS[lang]["color_green"], callback_data=f"{prefix}green", style="primary"),
         IKB(LANGS[lang]["color_purple"], callback_data=f"{prefix}purple", style="success")],
        [IKB(LANGS[lang]["color_black"], callback_data=f"{prefix}black", style="primary"),
         IKB(LANGS[lang]["color_white"], callback_data=f"{prefix}white", style="success"),
         IKB(LANGS[lang]["color_pink"], callback_data=f"{prefix}pink", style="primary")],
        [IKB(LANGS[lang]["color_cyan"], callback_data=f"{prefix}cyan", style="success"),
         IKB(LANGS[lang]["color_orange"], callback_data=f"{prefix}orange", style="primary"),
         IKB(LANGS[lang]["color_yellow"], callback_data=f"{prefix}yellow", style="success")],
        [IKB(LANGS[lang]["color_brown"], callback_data=f"{prefix}brown", style="primary"),
         IKB(LANGS[lang]["color_teal"], callback_data=f"{prefix}teal", style="success"),
         IKB(LANGS[lang]["color_lavender"], callback_data=f"{prefix}lavender", style="primary")],
        [IKB(LANGS[lang]["color_maroon"], callback_data=f"{prefix}maroon", style="success"),
         IKB(LANGS[lang]["color_navy"], callback_data=f"{prefix}navy", style="primary"),
         IKB(LANGS[lang]["color_olive"], callback_data=f"{prefix}olive", style="success")],
        [IKB(LANGS[lang]["color_coral"], callback_data=f"{prefix}coral", style="primary")],
    ]
    if include_dual and prefix == "color_":
        rows.append([IKB(LANGS[lang]["color_dual"], callback_data="color_dual", style="danger")])
    if include_back:
        rows.append([IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")])
    return rows

def _draw_text_maybe_split(draw, xy, text, font, fill):
    """
    يرسم النص عادي بلون واحد لو fill (r,g,b)،
    أو لو fill عبارة عن ((r1,g1,b1),(r2,g2,b2)) [اللون المشترك] يقسم النص لنصين
    ويرسم كل نص بلون، ويحسب مكان بداية النص التانى تلقائياً بعد نهاية الأول
    عشان مايحصلش تراكب أو فراغ - وده بيشتغل عادي مع أى نص حتى لو مزخرف.
    """
    if isinstance(fill, tuple) and len(fill) == 2 and isinstance(fill[0], tuple):
        color1, color2 = fill
        if not text:
            return
        mid = max(1, len(text) // 2)
        part1, part2 = text[:mid], text[mid:]
        x, y = xy
        draw.text((x, y), part1, font=font, fill=color1)
        if part2:
            try:
                bbox = draw.textbbox((x, y), part1, font=font)
                next_x = bbox[2]
            except Exception:
                w = draw.textlength(part1, font=font) if hasattr(draw, "textlength") else font.getsize(part1)[0]
                next_x = x + w
            draw.text((next_x, y), part2, font=font, fill=color2)
    else:
        draw.text(xy, text, font=font, fill=fill)

# مجلدات البحث عن الخطوط على السيرفر (لينكس أساساً، وويندوز لو محلي)
# مجلد "fonts" جنب السكربت مباشرة: أي خط تحطه هنا (زي NotoSansSymbols2-Regular.ttf
# أو Symbola.ttf عشان يدعم النصوص المزخرفة/الرموز الرياضية زي 𝓉𝒾𝓉ℴ) هيتلاقى تلقائي
# من غير ما نحتاج نعدل كود، وده أهم حل لمشكلة ظهور الخط بشكل غلط على ويندوز لأن
# خطوط لينكس دي مش موجودة على ويندوز افتراضياً.
LOCAL_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

FONT_SEARCH_DIRS = [
    LOCAL_FONTS_DIR,
    "/usr/share/fonts/truetype",
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.join(os.environ.get('WINDIR', ''), 'Fonts') if os.name == 'nt' else "",
]

_font_file_cache = {}

def _find_font_file(filename: str) -> Optional[str]:
    """يبحث عن ملف خط بالاسم داخل مجلدات الخطوط المعروفة على السيرفر (بحث متكرر)"""
    if filename in _font_file_cache:
        return _font_file_cache[filename]
    found = None
    for base in FONT_SEARCH_DIRS:
        if not base or not os.path.isdir(base):
            continue
        try:
            for root, _dirs, files in os.walk(base):
                if filename in files:
                    found = os.path.join(root, filename)
                    break
            if found:
                break
        except Exception:
            continue
    _font_file_cache[filename] = found
    return found

def _find_any_installed_font() -> Optional[str]:
    """آخر حل: يلاقي أي ملف .ttf/.otf موجود فعلياً على السيرفر بدل ما نرجع اسم وهمي"""
    for base in FONT_SEARCH_DIRS:
        if not base or not os.path.isdir(base):
            continue
        try:
            for root, _dirs, files in os.walk(base):
                for f in files:
                    if f.lower().endswith((".ttf", ".otf")):
                        return os.path.join(root, f)
        except Exception:
            continue
    return None

def get_font_path(font_name: str) -> str:
    """
    الحصول على مسار خط حقيقي موجود فعلياً على السيرفر.
    خطوط ويندوز الأصلية (Arial, Times...) غالباً مش موجودة على سيرفرات لينكس،
    فبندور على أول بديل متوافق فعلياً موجود، بدل ما نرجّع اسم ملف وهمي
    يخلي PIL يفشل ويستخدم خط احتياطي بدائي بيطلع استيكر غلط.
    """
    # كل نوع خط له قائمة بدائل بالأولوية (الاسم الأصلي، ثم بدائل حرة متوافقة شكلياً)
    font_candidates = {
        "arial":   ["arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "Carlito-Regular.ttf", "DejaVuSans.ttf", "FreeSans.ttf"],
        "bold":    ["arialbd.ttf", "Arial-Bold.ttf", "LiberationSans-Bold.ttf", "Carlito-Bold.ttf", "DejaVuSans-Bold.ttf", "FreeSansBold.ttf"],
        "times":   ["times.ttf", "Times New Roman.ttf", "LiberationSerif-Regular.ttf", "Caladea-Regular.ttf", "DejaVuSerif.ttf", "FreeSerif.ttf"],
        "courier": ["cour.ttf", "Courier New.ttf", "LiberationMono-Regular.ttf", "DejaVuSansMono.ttf", "FreeMono.ttf"],
        "impact":  ["impact.ttf", "Impact.ttf", "Anton-Regular.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
        "comic":   ["comic.ttf", "Comic Sans MS.ttf", "ComicNeue-Bold.ttf", "DejaVuSans.ttf"],
        # خطوط عربية حقيقية (كل واحد شكله مختلف فعلياً بدل ما كلهم يترجموا لـ Arial)
        "arabic":         ["NotoNaskhArabic-Regular.ttf", "Amiri-Regular.ttf", "FreeSerif.ttf"],
        "arabic_naskh":   ["NotoNaskhArabic-Regular.ttf", "Amiri-Regular.ttf", "FreeSerif.ttf"],
        "arabic_thuluth": ["Amiri-Regular.ttf", "NotoNaskhArabic-Regular.ttf"],
        "arabic_diwani":  ["Rakkas-Regular.ttf", "NotoNaskhArabic-Regular.ttf"],
        "arabic_ruqaa":   ["Katibeh-Regular.ttf", "NotoNaskhArabic-Regular.ttf"],
    }
    # الأنواع التانية كلها فعلياً بتترجم لنفس عائلة Arial في التصميم الأصلي
    # (الخطوط العربية بقى كل واحد منها ليه ملف خط حقيقي مستقل - شوف الفوق)
    alias_map = {
        "fancy": "arial", "script": "arial", "3d": "arial",
        "rounded": "arial", "graffiti": "arial", "old": "times", "modern": "arial",
        "english_gothic": "arial", "english_cursive": "arial",
        "english_modern": "arial",
    }
    base_key = alias_map.get(font_name, font_name)
    candidates = font_candidates.get(base_key, font_candidates["arial"])

    # 1) على ويندوز: دور فى مجلد الخطوط المحلي مباشرة
    if os.name == 'nt':
        fonts_dir = os.path.join(os.environ.get('WINDIR', ''), 'Fonts')
        for c in candidates:
            p = os.path.join(fonts_dir, c)
            if os.path.exists(p):
                return p

    # 2) دور فى مجلدات خطوط لينكس المعروفة عن أول بديل موجود فعلياً
    for c in candidates:
        p = _find_font_file(c)
        if p:
            return p

    # 3) آخر حل: أي خط TTF/OTF موجود فعلياً على السيرفر أياً كان (أفضل من خط وهمي غير موجود)
    any_font = _find_any_installed_font()
    if any_font:
        return any_font

    # 4) احتياط نظري أخير (المفروض متوصلش هنا لو فيه أي خط مثبت على السيرفر)
    return "arial.ttf"

# ========== نظام اختيار خط ذكي يدعم النصوص المزخرفة ورموز اليونيكود الخاصة ==========
# ملاحظة مهمة: خطوط زي Arial / Times / Impact / Comic Sans معندهاش رموز الرموز
# الرياضية/المزخرفة (زي 𝓉𝒾𝓉ℴ) ولا رموز الزالجو، فلو الخط المختار مش بيدعم
# حروف النص، لازم نلاقي خط بديل شامل بيدعمها فعلاً بدل ما يطلع استيكر فيه
# مربعات فاضية (tofu) أو شكل غلط تماماً.

# خطوط شاملة معروفة بدعمها لنطاق واسع جداً من اليونيكود (رموز رياضية، زخارف، زالجو...)
# رتبناها من الأشمل للأقل شمولاً - أول خط موجود فعلياً وبيغطي النص هو اللي هيتستخدم
FALLBACK_UNICODE_FONT_CANDIDATES = [
    # خطوط لو موجودة فى مجلد fonts/ المحلي (أو مثبتة على لينكس) هتغطي رموز/زخارف
    # يونيكود واسعة زي النصوص المزخرفة الرياضية (𝓉𝒾𝓉ℴ) والزالجو والرموز الخاصة
    # خطوط عربية حقيقية أولاً عشان النص العربي يطلع بشكل جميل بدل ما يقع على
    # FreeSerif (بديل مقبول بس مش جميل) أو يطلع تفح (tofu)
    "NotoNaskhArabic-Regular.ttf",
    "Amiri-Regular.ttf",
    "NotoSansSymbols2-Regular.ttf",
    "NotoSansSymbols-Regular.ttf",
    "NotoSansMath-Regular.ttf",
    "NotoSans-Regular.ttf",
    "FreeSerif.ttf",
    "FreeSans.ttf",
    "DejaVuSans.ttf",
    "Symbola.ttf",
    "unifont.ttf",
    "SourceHanSans-Regular.ttf",
    # بدائل موجودة افتراضياً على ويندوز (تغطي جزء كبير من الرموز والزخارف الرياضية)
    "seguisym.ttf",     # Segoe UI Symbol
    "seguiemj.ttf",     # Segoe UI Emoji
    "cambria.ttc",       # Cambria Math غالباً هيغطي الحروف المزخرفة الرياضية
    "cambriab.ttf",
]

_font_cmap_cache = {}

def _font_covers_text(font_path: str, text: str) -> bool:
    """يتأكد إن الخط المحدد فعلاً بيحتوي على كل حروف النص (باستخدام جدول cmap)"""
    if not font_path or not text:
        return True
    try:
        from fontTools.ttLib import TTFont
    except Exception:
        # لو المكتبة مش متاحة، منقدرش نتأكد فنسيب PIL يحاول
        return True
    try:
        if font_path not in _font_cmap_cache:
            cmap_set = set()
            # ملفات .ttc (زي Cambria/Cambria Math) ممكن يكون فيها أكتر من خط جوه نفس الملف،
            # فبنجمع حروف كل الخطوط الموجودة فى الملف عشان مانفوتش تغطية موجودة فى خط تاني رقمه غير 0
            font_numbers = range(4) if font_path.lower().endswith(".ttc") else [0]
            for fn in font_numbers:
                try:
                    tt = TTFont(font_path, lazy=True, fontNumber=fn)
                    for table in tt['cmap'].tables:
                        try:
                            cmap_set |= set(table.cmap.keys())
                        except Exception:
                            continue
                except Exception:
                    break
            _font_cmap_cache[font_path] = cmap_set
        cmap_set = _font_cmap_cache[font_path]
        for ch in text:
            if ch.isspace():
                continue
            if ord(ch) not in cmap_set:
                return False
        return True
    except Exception:
        return True

def get_smart_font_path(font_name: str, text: str = "") -> str:
    """
    يرجع مسار الخط الأنسب لعرض النص:
    - لو النص عادي والخط المختار بيدعمه: يرجع نفس الخط زي ما هو.
    - لو النص فيه رموز/زخارف يونيكود خاصة (مزخرف بأي نمط) والخط الأساسي
      مش بيدعمها: يدوّر على أول خط شامل موجود فعلاً على السيرفر وبيدعم
      كل حروف النص، عشان الزخرفة تتطبق وتظهر صح بدل ما تطلع مربعات أو شكل غلط.
    """
    base_path = get_font_path(font_name)

    if text and not _font_covers_text(base_path, text):
        # الخط الأساسي مش بيغطي كل الحروف - دوّر على بديل شامل يغطيها
        for candidate in FALLBACK_UNICODE_FONT_CANDIDATES:
            path = _find_font_file(candidate)
            if path and _font_covers_text(path, text):
                return path
        # لو ولا خط غطى النص بالكامل، خد أفضل خط بديل موجود على الأقل
        # (أشمل من Arial حتى لو مش هيغطي 100% من رموز نادرة جداً)
        for candidate in FALLBACK_UNICODE_FONT_CANDIDATES:
            path = _find_font_file(candidate)
            if path:
                return path

    return base_path

async def is_member(uid: int, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من اشتراك المستخدم في القناة"""
    try:
        member = await ctx.bot.get_chat_member(CHANNEL_ID, uid)
        return member.status in {"member", "administrator", "creator"}
    except Exception as e:
        print(f"Error checking membership: {e}")
        return False

def generate_sticker_set_name(user_id: int, suffix: str = "") -> str:
    """توليد اسم حزمة ملصقات صالح لـ Telegram"""
    import random
    import string
    
    # إنشاء سلسلة عشوائية قصيرة
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    
    # الحصول على التوقيت الحالي
    timestamp = int(time.time())
    
    # إزالة أي أحرف غير مسموح بها
    bot_name = BOT_USERNAME.replace("@", "").replace(".", "_").lower()
    
    # بناء الاسم
    base_name = f"sticker_{timestamp}_{random_str}"
    
    # التأكد من أن الاسم يبدأ بحرف وليس رقماً
    if base_name[0].isdigit():
        base_name = f"s{base_name}"
    
    # إضافة اسم البوت (مطلوب من تليجرام)
    full_name = f"{base_name}_by_{bot_name}"
    
    # تنظيف الاسم
    full_name = sanitize_sticker_set_name(full_name)
    
    print(f"Generated sticker set name: {full_name}")
    return full_name

def generate_unique_sticker_set_name(user_id: int, is_video: bool = False) -> str:
    """توليد اسم حزمة استيكرات فريد ومتوافق مع تليجرام"""
    import random
    import string
    
    # إنشاء سلسلة عشوائية قصيرة
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    
    # الحصول على التوقيت الحالي
    timestamp = int(time.time())
    
    # إزالة أي أحتر غير مسموح بها
    bot_name = BOT_USERNAME.replace("@", "").replace(".", "_").lower()
    
    # بناء الاسم مع التأكد من عدم تجاوز الحد الأقصى
    if is_video:
        base_name = f"video_{timestamp}_{random_str}"
    else:
        base_name = f"sticker_{timestamp}_{random_str}"
    
    # التأكد من أن الاسم يبدأ بحرف وليس رقماً
    if base_name[0].isdigit():
        base_name = f"s{base_name}"
    
    # إضافة اسم البوت (مطلوب من تليجرام)
    full_name = f"{base_name}_by_{bot_name}"
    
    # تنظيف الاسم
    full_name = sanitize_sticker_set_name(full_name)
    
    print(f"Generated unique sticker set name: {full_name}")
    return full_name

def sanitize_sticker_set_name(name: str) -> str:
    """تنظيف اسم حزمة الاستيكرات"""
    # إزالة الأحرف غير المسموح بها
    name = re.sub(r'[^a-z0-9_]', '', name.lower())
    
    # التأكد من أن الاسم يبدأ بحرف
    if name and name[0].isdigit():
        name = f"s{name}"
    
    # تقصير الاسم إذا كان طويلاً
    if len(name) > 64:
        name = name[:64]
    
    return name

async def check_sticker_set_exists(ctx, set_name, user_id):
    """فحص ما إذا كانت حزمة الاستيكرات موجودة"""
    try:
        sticker_set = await ctx.bot.get_sticker_set(set_name)
        return True
    except Exception as e:
        print(f"Sticker set not found yet: {e}")
        return False

# ========== Image Validation ==========
def validate_image_dimensions(image_path: str, target_size: tuple = (100, 100)) -> str:
    """التحقق من أبعاد الصورة وإصلاحها إذا لزم الأمر"""
    try:
        with Image.open(image_path) as img:
            # تحويل إلى RGBA إذا لزم الأمر
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # التحقق من الأبعاد
            if img.size != target_size:
                print(f"Resizing image from {img.size} to {target_size}")
                img = img.resize(target_size, Image.LANCZOS)
                
                # حفظ الصورة المصححة
                corrected_path = f"{tempfile.gettempdir()}/corrected_{uuid.uuid4().hex}.png"
                img.save(corrected_path, "PNG", optimize=True)
                
                return corrected_path
        
        return image_path
    except Exception as e:
        print(f"Error validating image dimensions: {e}")
        return image_path

# ========== Compression Functions ==========
def compress_image(input_path: str, max_size_kb: int = 256) -> str:
    """ضغط صورة لتقليل حجمها للرموز المميزة"""
    try:
        with Image.open(input_path) as img:
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            output_path = f"{tempfile.gettempdir()}/emoji_compressed_{uuid.uuid4().hex}.png"
            
            # حفظ بجودة عالية أولاً
            img.save(output_path, 'PNG', optimize=True, quality=95)
            file_size = os.path.getsize(output_path) / 1024
            
            # إذا كان الحجم أكبر من الحد، نضغط أكثر
            if file_size > max_size_kb:
                quality = 90
                while quality > 30 and file_size > max_size_kb:
                    img.save(output_path, 'PNG', optimize=True, quality=quality)
                    file_size = os.path.getsize(output_path) / 1024
                    quality -= 10
            
            print(f"Image compressed to: {file_size:.1f}KB")
            return output_path
    except Exception as e:
        print(f"Error compressing image: {e}")
        return input_path

def compress_image_aggressive(input_path: str, max_size_kb: int = 256) -> str:
    """ضغط صورة بقوة أكبر للرموز المميزة"""
    try:
        with Image.open(input_path) as img:
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            output_path = f"{tempfile.gettempdir()}/emoji_aggressive_{uuid.uuid4().hex}.png"
            
            # تقليل الأبعاد أولاً
            img.thumbnail((96, 96), Image.LANCZOS)
            
            # حفظ بجودة منخفضة
            quality = 50
            img.save(output_path, 'PNG', optimize=True, quality=quality)
            file_size = os.path.getsize(output_path) / 1024
            
            # إذا كان الحجم لا يزال كبيراً، نضغط أكثر
            if file_size > max_size_kb:
                quality = 40
                while quality > 10 and file_size > max_size_kb:
                    img.save(output_path, 'PNG', optimize=True, quality=quality)
                    file_size = os.path.getsize(output_path) / 1024
                    quality -= 5
            
            print(f"Aggressive image compression: {file_size:.1f}KB")
            return output_path
    except Exception as e:
        print(f"Error in aggressive compression: {e}")
        return compress_image(input_path, max_size_kb)

# ========== Advanced Video Processing ==========
def process_video_to_webm_advanced(input_path: str, max_duration: int = 3, max_size_kb: int = 256, target_size: int = 100) -> str:
    """معالجة الفيديو وتحويله إلى WebM متوافق مع الرموز المميزة/الاستيكرات العادية
    target_size: 100 للرموز المميزة (custom emoji) و 512 للاستيكرات العادية (regular)"""
    try:
        output_path = f"{tempfile.gettempdir()}/emoji_advanced_{uuid.uuid4().hex}.webm"
        
        # فحص تنسيق الفيديو
        try:
            probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=codec_name,duration,width,height',
                        '-of', 'csv=p=0', input_path]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
            print(f"Video probe: {probe_result.stdout}")
        except:
            print("Could not probe video, using default settings")
        
        # تحويل إلى WebM مع إعدادات محددة (الحجم بيتحدد حسب نوع الاستيكر)
        cmd = [
            'ffmpeg', '-i', input_path,
            '-t', str(max_duration),  # قص إلى 3 ثواني
            '-vf', f'scale={target_size}:{target_size}:force_original_aspect_ratio=decrease,pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
            '-c:v', 'libvpx-vp9',  # كودك VP9 الأحدث
            '-pix_fmt', 'yuv420p',
            '-b:v', '200k',  # تقليل البت ريت
            '-crf', '40',  # زيادة الضغط
            '-quality', 'good',
            '-cpu-used', '4',
            '-row-mt', '1',
            '-tile-columns', '2',
            '-frame-parallel', '1',
            '-lag-in-frames', '25',
            '-g', '240',
            '-an',  # إزالة الصوت
            '-r', '20',  # تقليل معدل الإطارات
            '-movflags', '+faststart',
            '-f', 'webm',
            '-y', output_path
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr}")
            # محاولة بإعدادات أبسط
            return process_video_to_webm_simple(input_path, max_duration, max_size_kb, target_size)
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path) / 1024
            print(f"Advanced WebM created: {file_size:.1f}KB")
            
            # إذا كان الحجم كبيراً جداً، نضغط أكثر
            if file_size > max_size_kb:
                compressed_path = compress_video_for_emoji(output_path, max_size_kb, target_size)
                if compressed_path != output_path:
                    os.remove(output_path)
                return compressed_path
            
            return output_path
        
        return input_path
    except subprocess.TimeoutExpired:
        print("FFmpeg timeout, trying simple method")
        return process_video_to_webm_simple(input_path, max_duration, max_size_kb, target_size)
    except Exception as e:
        print(f"Advanced video processing error: {e}")
        return process_video_to_webm_simple(input_path, max_duration, max_size_kb, target_size)

def process_video_to_webm_simple(input_path: str, max_duration: int = 3, max_size_kb: int = 256, target_size: int = 100) -> str:
    """طريقة أبسط لتحويل الفيديو إلى WebM"""
    try:
        output_path = f"{tempfile.gettempdir()}/emoji_simple_{uuid.uuid4().hex}.webm"
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-t', str(max_duration),
            '-vf', f'scale={target_size}:{target_size}:force_original_aspect_ratio=decrease,pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
            '-c:v', 'libvpx',  # كودك قديم لكن متوافق
            '-pix_fmt', 'yuv420p',
            '-b:v', '150k',  # تقليل البت ريت
            '-crf', '50',  # زيادة الضغط
            '-deadline', 'good',
            '-an',
            '-r', '15',  # معدل إطارات أقل
            '-g', '30',
            '-threads', '2',
            '-f', 'webm',
            '-y', output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path) / 1024
            print(f"Simple WebM created: {file_size:.1f}KB")
            
            if file_size > max_size_kb:
                return compress_video_for_emoji(output_path, max_size_kb, target_size)
            
            return output_path
        
        # إذا فشل WebM، نجرب MP4
        return convert_to_mp4_fallback(input_path, max_duration, max_size_kb)
    except Exception as e:
        print(f"Simple video processing error: {e}")
        return convert_to_mp4_fallback(input_path, max_duration, max_size_kb)

def convert_to_mp4_fallback(input_path: str, max_duration: int = 3, max_size_kb: int = 256) -> str:
    """الرجوع إلى MP4 إذا فشل WebM"""
    try:
        output_path = f"{tempfile.gettempdir()}/emoji_fallback_{uuid.uuid4().hex}.mp4"
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-t', str(max_duration),
            '-vf', 'scale=100:100',
            '-c:v', 'libx264',
            '-b:v', '150k',  # تقليل البت ريت
            '-crf', '32',  # زيادة الضغط
            '-an',
            '-r', '15',
            '-g', '30',
            '-preset', 'fast',
            '-pix_fmt', 'yuv420p',
            '-y', output_path
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path) / 1024
            print(f"MP4 fallback created: {file_size:.1f}KB")
            
            if file_size > max_size_kb:
                # محاولة ضغط MP4
                compressed_mp4 = compress_video_for_emoji(output_path, max_size_kb)
                if compressed_mp4 != output_path:
                    os.remove(output_path)
                return compressed_mp4
            
            return output_path
        
        return input_path
    except Exception as e:
        print(f"MP4 fallback error: {e}")
        return input_path

def compress_video_for_emoji(input_path: str, max_size_kb: int = 256, target_size: int = 100) -> str:
    """ضغط فيديو للرموز المميزة/الاستيكرات العادية"""
    try:
        # معرفة تنسيق الملف
        if input_path.endswith('.mp4'):
            # تحويل MP4 إلى WebM أولاً
            temp_webm = f"{tempfile.gettempdir()}/temp_webm_{uuid.uuid4().hex}.webm"
            cmd_convert = [
                'ffmpeg', '-i', input_path,
                '-vf', f'scale={target_size}:{target_size}:force_original_aspect_ratio=decrease,pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
                '-c:v', 'libvpx',
                '-pix_fmt', 'yuv420p',
                '-b:v', '100k',
                '-crf', '50',
                '-an',
                '-r', '10',
                '-f', 'webm',
                '-y', temp_webm
            ]
            subprocess.run(cmd_convert, capture_output=True, text=True, timeout=30)
            
            if os.path.exists(temp_webm):
                os.remove(input_path)
                input_path = temp_webm
        
        # ضغط الفيديو النهائي (نحافظ على نفس أبعاد الاستيكر المطلوبة)
        output_path = f"{tempfile.gettempdir()}/emoji_compressed_video_{uuid.uuid4().hex}.webm"
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-vf', f'scale={target_size}:{target_size}:force_original_aspect_ratio=decrease,pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
            '-c:v', 'libvpx',
            '-pix_fmt', 'yuv420p',
            '-b:v', '80k',  # بت ريت منخفض
            '-crf', '55',  # ضغط عالي
            '-deadline', 'best',
            '-an',
            '-r', '8',  # معدل إطارات منخفض
            '-g', '15',
            '-threads', '4',
            '-f', 'webm',
            '-y', output_path
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path) / 1024
            print(f"Video compressed to: {file_size:.1f}KB")
            
            if file_size > max_size_kb:
                # محاولة أكثر قوة
                return compress_video_extreme(input_path, max_size_kb, target_size)
            
            return output_path
        
        return input_path
    except Exception as e:
        print(f"Video compression error: {e}")
        return compress_video_extreme(input_path, max_size_kb, target_size)

def compress_video_extreme(input_path: str, max_size_kb: int = 256, target_size: int = 100) -> str:
    """ضغط فيديو شديد - بيحافظ على نفس أبعاد الاستيكر المطلوبة (بس بجودة أقل)"""
    try:
        output_path = f"{tempfile.gettempdir()}/emoji_extreme_{uuid.uuid4().hex}.webm"
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-vf', f'scale={target_size}:{target_size}:force_original_aspect_ratio=decrease,pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
            '-c:v', 'libvpx',
            '-pix_fmt', 'yuv420p',
            '-b:v', '40k',  # بت ريت منخفض جداً
            '-crf', '60',  # جودة منخفضة جداً
            '-an',
            '-r', '5',  # معدل إطارات منخفض جداً
            '-g', '10',
            '-threads', '4',
            '-quality', 'realtime',
            '-f', 'webm',
            '-y', output_path
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path) / 1024
            print(f"Extreme compression: {file_size:.1f}KB")
            
            if file_size > max_size_kb:
                # قص المدة إلى 2 ثانية فقط
                return compress_video_final(input_path, max_size_kb, target_size)
            
            return output_path
        
        return input_path
    except Exception as e:
        print(f"Extreme compression error: {e}")
        return compress_video_final(input_path, max_size_kb, target_size)

def compress_video_final(input_path: str, max_size_kb: int = 256, target_size: int = 100) -> str:
    """الضغط النهائي للفيديو - بيحافظ برضه على أبعاد الاستيكر الصحيحة"""
    try:
        output_path = f"{tempfile.gettempdir()}/emoji_final_{uuid.uuid4().hex}.webm"
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-t', '2',  # 2 ثانية فقط
            '-vf', f'scale={target_size}:{target_size}:force_original_aspect_ratio=decrease,pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,format=yuv420p',
            '-c:v', 'libvpx',
            '-pix_fmt', 'yuv420p',
            '-b:v', '20k',  # بت ريت منخفض جداً
            '-crf', '63',
            '-an',
            '-r', '3',  # 3 إطارات في الثانية فقط
            '-g', '5',
            '-quality', 'realtime',
            '-f', 'webm',
            '-y', output_path
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        return output_path if os.path.exists(output_path) else input_path
    except Exception as e:
        print(f"Final compression error: {e}")
        return input_path

def process_gif_to_webm_advanced(input_path: str, target_size: int = 100, max_size_kb: int = 256) -> str:
    """معالجة GIF متقدمة وتحويله إلى WebM
    target_size: 100 للرموز المميزة (custom emoji) و 512 للاستيكرات العادية (regular)
    ملحوظة: الفلاتر القديمة (palettegen/paletteuse) بتولد صورة "pal8" مخصصة لصيغة GIF،
    وده بيتعارض مع كودك VP9 اللي محتاج yuv420p، فكان بيطلع ملف WebM تالف/فاسد
    ولذلك تلجرام كان بيرفضه بخطأ Sticker_video_nowebm. اتشالت الفلاتر دي واتستبدلت
    بتحويل مباشر لصيغة yuv420p المتوافقة مع VP9."""
    try:
        output_path = f"{tempfile.gettempdir()}/gif_advanced_{uuid.uuid4().hex}.webm"
        
        # تحويل GIF إلى WebM بصيغة بكسل متوافقة مع VP9
        cmd = [
            'ffmpeg', '-i', input_path,
            '-t', '3',  # قص إلى 3 ثواني
            '-vf', f'scale={target_size}:{target_size}:force_original_aspect_ratio=decrease,pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,fps=15,format=yuv420p',
            '-c:v', 'libvpx-vp9',
            '-pix_fmt', 'yuv420p',
            '-b:v', '150k',  # تقليل البت ريت
            '-crf', '40',  # زيادة الضغط
            '-quality', 'good',
            '-an',
            '-f', 'webm',
            '-y', output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path) / 1024
            print(f"GIF to WebM: {file_size:.1f}KB")
            
            if file_size > max_size_kb:
                # ضغط GIF
                return compress_gif_for_emoji(input_path, target_size, max_size_kb)
            
            return output_path
        
        print(f"GIF ffmpeg error: {result.stderr}")
        return process_gif_to_webm_simple(input_path, target_size, max_size_kb)
    except Exception as e:
        print(f"GIF processing error: {e}")
        return process_gif_to_webm_simple(input_path, target_size, max_size_kb)

def process_gif_to_webm_simple(input_path: str, target_size: int = 100, max_size_kb: int = 256) -> str:
    """طريقة أبسط لتحويل GIF"""
    try:
        output_path = f"{tempfile.gettempdir()}/gif_simple_{uuid.uuid4().hex}.webm"
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-t', '3',
            '-vf', f'scale={target_size}:{target_size}:force_original_aspect_ratio=decrease,pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,fps=10,format=yuv420p',  # تقليل FPS أكثر
            '-c:v', 'libvpx',
            '-pix_fmt', 'yuv420p',
            '-b:v', '100k',  # بت ريت أقل
            '-crf', '50',  # ضغط أكثر
            '-an',
            '-f', 'webm',
            '-y', output_path
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        return output_path if os.path.exists(output_path) else input_path
    except Exception as e:
        print(f"Simple GIF processing error: {e}")
        return input_path

def compress_gif_for_emoji(input_path: str, target_size: int = 100, max_size_kb: int = 256) -> str:
    """ضغط GIF للرموز المميزة/الاستيكرات العادية - بيحافظ على نفس أبعاد الاستيكر المطلوبة
    (تلجرام برفض أي أبعاد غير 100x100 للرموز المميزة أو 512x512 للاستيكر العادي)"""
    try:
        output_path = f"{tempfile.gettempdir()}/gif_compressed_{uuid.uuid4().hex}.webm"
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-t', '2',  # قص أكثر
            '-vf', f'scale={target_size}:{target_size}:force_original_aspect_ratio=decrease,pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih)/2,fps=8,format=yuv420p',
            '-c:v', 'libvpx',
            '-pix_fmt', 'yuv420p',
            '-b:v', '60k',  # بت ريت أقل جداً
            '-crf', '58',  # ضغط أكثر
            '-an',
            '-f', 'webm',
            '-y', output_path
        ]
        
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        return output_path if os.path.exists(output_path) else input_path
    except Exception as e:
        print(f"GIF compression error: {e}")
        return input_path

# ========== كشف النص المزخرف مسبقاً وحمايته من إعادة التشكيل ==========
import unicodedata

def is_fancy_decorated_text(text: str) -> bool:
    """
    يكتشف إذا كان النص مُزخرف بالفعل (أي نمط زخرفة - عربي، إنجليزي، زالجو،
    رموز يونيكود خاصة، أشكال عرض جاهزة...) بحيث لا نلمسه أو نغيّر فيه.
    """
    if not text:
        return False

    stripped = text.strip()
    if not stripped:
        return False

    total = len(stripped)
    fancy_count = 0

    for ch in stripped:
        code = ord(ch)
        category = unicodedata.category(ch)

        # علامات تراكب/تشكيل زائدة (زالجو وما شابهه)
        if category in ("Mn", "Me", "Mc"):
            fancy_count += 1
            continue

        # حروف عربية عادية (غير مُشكَّلة مسبقاً) أو مسافات/أرقام/علامات ترقيم أساسية
        if (0x0600 <= code <= 0x06FF) or (0x0750 <= code <= 0x077F):
            continue
        if ch.isspace() or ch in "0123456789.,!?-_():;\"'":
            continue
        # حروف لاتينية عادية (a-z, A-Z)
        if ch.isascii() and ch.isalpha():
            continue

        # أي شيء آخر (رموز خاصة، حروف مزخرفة، أشكال عرض عربية جاهزة، رموز رياضية...) = زخرفة
        fancy_count += 1

    ratio = fancy_count / total
    return ratio >= 0.15


def smart_reshape_text(text: str) -> str:
    """
    - لو النص مزخرف بالفعل (بأي أسلوب أو نوع زخرفة): يرجع زي ما هو تماماً بدون أي تعديل.
    - لو نص عربي عادي (غير مزخرف): يتم تشكيله وضبط اتجاهه للعرض الصحيح.
    - لو إنجليزي عادي: يرجع زي ما هو.
    """
    try:
        if is_fancy_decorated_text(text):
            return text
        reshaped_text = arabic_reshaper.reshape(text)
        return get_display(reshaped_text)
    except Exception:
        return text


# ========== Advanced Arabic/English Decoration Effects ==========
def apply_arabic_calligraphy_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont, 
                                  x: int, y: int, ww: int, hh: int, fill_color: tuple,
                                  center_y: float = None, max_h: int = 74) -> Image.Image:
    """تطبيق تأثير الخط العربي المزخرف"""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    
    # إعادة تشكيل النص العربي (يتخطى أي نص مزخرف بالفعل ويتركه كما هو)
    display_text = smart_reshape_text(text)
    
    # حجم خط أكبر للخط العربي المزخرف - يُضبط تلقائياً ليتسع النص كاملاً مع مساحة للزخارف حوله
    try:
        _tmp_draw = ImageDraw.Draw(result)
        arabic_font, _ = _fit_font_size(_tmp_draw, get_smart_font_path("arabic", display_text), [display_text], 45, 74, max_h)
    except:
        arabic_font = font
    
    # إعادة حساب الموقع مع الخط الجديد
    try:
        bbox = draw.textbbox((0, 0), display_text, font=arabic_font)
    except:
        bbox = (0, 0, ww, hh)
    
    new_ww = bbox[2] - bbox[0]
    new_hh = bbox[3] - bbox[1]
    new_x = (100 - new_ww) / 2
    new_y = center_y - new_hh / 2 if center_y is not None else (100 - new_hh) / 2
    
    # رسم تأثير الخط العربي المزخرف
    shadow_depth = 4
    for i in range(shadow_depth, 0, -1):
        shadow_color = (0, 0, 0, 30 + i*15)
        draw.text((new_x + i, new_y + i), display_text, font=arabic_font, fill=shadow_color)
    
    # النص الأساسي
    _draw_text_maybe_split(draw, (new_x, new_y), display_text, arabic_font, fill_color)
    
    # الزخارف التلقائية (نقاط وخطوط) بتتضاف بس لو النص مش مزخرف بالفعل من المستخدم -
    # لو المستخدم بعت نص مزخرف جاهز، بنسيبه بدون أي خلفية أو إطار زيادة، النص + اللون + التأثيرات بس
    if not is_fancy_decorated_text(text):
        ornament_color = (255, 215, 0, 180)  # ذهبي
        ornament_size = 2
        
        # نقاط الزخرفة حول النص
        points = [
            (new_x - 5, new_y + hh//2),
            (new_x + new_ww + 5, new_y + hh//2),
            (new_x + new_ww//2, new_y - 5),
            (new_x + new_ww//2, new_y + hh + 5),
        ]
        
        for px, py in points:
            draw.ellipse([px-ornament_size, py-ornament_size, px+ornament_size, py+ornament_size], 
                        fill=ornament_color)
        
        # خطوط زخرفية
        for i in range(3):
            line_y = new_y + hh + 5 + i*2
            draw.line([(new_x - 3, line_y), (new_x + new_ww + 3, line_y)], 
                     fill=ornament_color, width=1)
    
    return result

def apply_english_fancy_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                             x: int, y: int, ww: int, hh: int, fill_color: tuple,
                             center_y: float = None, max_h: int = 76) -> Image.Image:
    """تطبيق تأثير الزخرفة الإنجليزية"""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    
    # حجم خط أكبر للزخرفة الإنجليزية - يُضبط تلقائياً ليتسع النص كاملاً مع مساحة للإطار حوله
    try:
        fancy_font, _ = _fit_font_size(draw, get_smart_font_path("english_cursive", text), [text], 42, 76, max_h)
    except:
        fancy_font = font
    
    # إعادة حساب الموقع
    try:
        bbox = draw.textbbox((0, 0), text, font=fancy_font)
    except:
        bbox = (0, 0, ww, hh)
    
    new_ww = bbox[2] - bbox[0]
    new_hh = bbox[3] - bbox[1]
    new_x = (100 - new_ww) / 2
    new_y = center_y - new_hh / 2 if center_y is not None else (100 - new_hh) / 2
    
    # تأثير التدرج اللوني للنص
    # (بنستخدم لون واحد ممثل حتى لو اللون المختار "لون مشترك" لتفادي خطأ القسمة على تيوبل)
    _solid = _solid_fill_color(fill_color)
    gradient_colors = [
        (255, 255, 255, 200),  # أبيض
        _solid,
        (_solid[0]//2, _solid[1]//2, _solid[2]//2, 255)  # أغمق
    ]
    
    # رسم النص بتأثير التدرج
    for i, color in enumerate(gradient_colors):
        offset = i * 0.7
        draw.text((new_x + offset, new_y + offset), text, font=fancy_font, fill=color)
    
    # الإطار والزخارف حول النص بتتضاف بس لو النص مش مزخرف بالفعل من المستخدم -
    # لو النص جاي مزخرف جاهز من المستخدم، بنسيبه شفاف بدون أي إطار زيادة
    if not is_fancy_decorated_text(text):
        # إطار فاخر حول النص
        frame_color = (255, 215, 0, 150)  # ذهبي شفاف
        frame_margin = 3
        draw.rounded_rectangle(
            [new_x - frame_margin, new_y - frame_margin, 
             new_x + new_ww + frame_margin, new_y + new_hh + frame_margin],
            radius=10,
            outline=frame_color,
            width=2
        )
        
        # زوايا مزخرفة
        corner_size = 8
        corners = [
            (new_x - frame_margin, new_y - frame_margin),
            (new_x + new_ww + frame_margin - corner_size, new_y - frame_margin),
            (new_x - frame_margin, new_y + new_hh + frame_margin - corner_size),
            (new_x + new_ww + frame_margin - corner_size, new_y + new_hh + frame_margin - corner_size)
        ]
        
        for cx, cy in corners:
            draw.rectangle([cx, cy, cx + corner_size, cy + corner_size], 
                          outline=frame_color, width=2)
    
    return result

def apply_arabic_pattern_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                              x: int, y: int, ww: int, hh: int, fill_color: tuple,
                              center_y: float = None, max_h: int = 70) -> Image.Image:
    """تطبيق تأثير الزخارف العربية التقليدية"""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    
    # إعادة تشكيل النص العربي (يتخطى أي نص مزخرف بالفعل ويتركه كما هو)
    display_text = smart_reshape_text(text)
    
    # حجم خط كبير - يُضبط تلقائياً ليتسع النص كاملاً مع مساحة للزخارف حوله
    try:
        arabic_font, _ = _fit_font_size(draw, get_smart_font_path("arabic", display_text), [display_text], 44, 70, max_h)
    except:
        arabic_font = font
    
    # إعادة حساب الموقع
    try:
        bbox = draw.textbbox((0, 0), display_text, font=arabic_font)
    except:
        bbox = (0, 0, ww, hh)
    
    new_ww = bbox[2] - bbox[0]
    new_hh = bbox[3] - bbox[1]
    new_x = (100 - new_ww) / 2
    new_y = center_y - new_hh / 2 if center_y is not None else (100 - new_hh) / 2
    
    # النص الأساسي مع ظل
    shadow_color = (0, 0, 0, 100)
    for i in range(3, 0, -1):
        draw.text((new_x + i, new_y + i), display_text, font=arabic_font, fill=shadow_color)
    
    _draw_text_maybe_split(draw, (new_x, new_y), display_text, arabic_font, fill_color)
    
    # الزخارف العربية التقليدية (أرابيسك) بتتضاف بس لو النص مش مزخرف بالفعل من المستخدم
    if not is_fancy_decorated_text(text):
        pattern_color = (139, 69, 19, 180)  # لون خشبي
        pattern_color2 = (210, 180, 140, 150)  # لون عاجي
        
        # أنماط زخرفية حول النص
        pattern_points = [
            # زوايا
            (new_x - 8, new_y - 8),
            (new_x + new_ww + 8, new_y - 8),
            (new_x - 8, new_y + new_hh + 8),
            (new_x + new_ww + 8, new_y + new_hh + 8),
            # منتصف الأضلاع
            (new_x + new_ww//2, new_y - 8),
            (new_x + new_ww//2, new_y + new_hh + 8),
            (new_x - 8, new_y + new_hh//2),
            (new_x + new_ww + 8, new_y + new_hh//2)
        ]
        
        for px, py in pattern_points:
            # رسم زخارف دائرية
            draw.ellipse([px-3, py-3, px+3, py+3], fill=pattern_color)
            draw.ellipse([px-1, py-1, px+1, py+1], fill=pattern_color2)
        
        # خطوط زخرفية متصلة
        draw.line([(new_x - 5, new_y - 5), (new_x + new_ww + 5, new_y - 5)], 
                 fill=pattern_color, width=2)
        draw.line([(new_x - 5, new_y + new_hh + 5), (new_x + new_ww + 5, new_y + new_hh + 5)], 
                 fill=pattern_color, width=2)
    
    return result

def apply_english_pattern_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                               x: int, y: int, ww: int, hh: int, fill_color: tuple,
                               center_y: float = None, max_h: int = 70) -> Image.Image:
    """تطبيق تأثير الزخارف الإنجليزية"""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    
    # حجم خط كبير - يُضبط تلقائياً ليتسع النص كاملاً مع مساحة للزخارف حوله
    try:
        pattern_font, _ = _fit_font_size(draw, get_smart_font_path("english_gothic", text), [text], 46, 70, max_h)
    except:
        pattern_font = font
    
    # إعادة حساب الموقع
    try:
        bbox = draw.textbbox((0, 0), text, font=pattern_font)
    except:
        bbox = (0, 0, ww, hh)
    
    new_ww = bbox[2] - bbox[0]
    new_hh = bbox[3] - bbox[1]
    new_x = (100 - new_ww) / 2
    new_y = center_y - new_hh / 2 if center_y is not None else (100 - new_hh) / 2
    
    # تأثير نص متعدد الطبقات
    layer_colors = [
        (0, 0, 0, 150),  # ظل أسود
        (50, 50, 50, 120),  # رمادي داكن
        (100, 100, 100, 90),  # رمادي متوسط
        fill_color  # اللون الأساسي
    ]
    
    for i, color in enumerate(layer_colors):
        offset = i * 1.2
        draw.text((new_x + offset, new_y + offset), text, font=pattern_font, fill=color)
    
    # الإطار والزخارف الإنجليزية بتتضاف بس لو النص مش مزخرف بالفعل من المستخدم
    if not is_fancy_decorated_text(text):
        frame_colors = [(139, 69, 19, 200), (210, 180, 140, 180)]  # ألوان خشبية
        
        # إطار خارجي
        draw.rectangle(
            [new_x - 6, new_y - 6, new_x + new_ww + 6, new_y + new_hh + 6],
            outline=frame_colors[0],
            width=3
        )
        
        # إطار داخلي
        draw.rectangle(
            [new_x - 3, new_y - 3, new_x + new_ww + 3, new_y + new_hh + 3],
            outline=frame_colors[1],
            width=2
        )
        
        # زخارف زاوية إنجليزية
        corner_decor = [
            # الزاوية العلوية اليسرى
            [(new_x - 6, new_y - 6), (new_x - 1, new_y - 6), (new_x - 6, new_y - 1)],
            # الزاوية العلوية اليمنى
            [(new_x + new_ww + 6, new_y - 6), (new_x + new_ww + 1, new_y - 6), (new_x + new_ww + 6, new_y - 1)],
            # الزاوية السفلية اليسرى
            [(new_x - 6, new_y + new_hh + 6), (new_x - 1, new_y + new_hh + 6), (new_x - 6, new_y + new_hh + 1)],
            # الزاوية السفلية اليمنى
            [(new_x + new_ww + 6, new_y + new_hh + 6), (new_x + new_ww + 1, new_y + new_hh + 6), (new_x + new_ww + 6, new_y + new_hh + 1)]
        ]
        
        for corner in corner_decor:
            draw.polygon(corner, fill=frame_colors[0])
        
        # نقاط زخرفية
        for i in range(4):
            dot_x = new_x + (i + 1) * (new_ww // 5)
            for j in range(2):
                dot_y = new_y - 8 if j == 0 else new_y + new_hh + 8
                draw.ellipse([dot_x-2, dot_y-2, dot_x+2, dot_y+2], fill=frame_colors[1])
    
    return result

def apply_arabic_ornament_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                               x: int, y: int, ww: int, hh: int, fill_color: tuple) -> Image.Image:
    """تطبيق تأثير الزخرفة العربية المتقدمة"""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    
    # إعادة تشكيل النص العربي (يتخطى أي نص مزخرف بالفعل ويتركه كما هو)
    display_text = smart_reshape_text(text)
    
    # حجم خط كبير جداً للزخرفة - يُضبط تلقائياً ليتسع النص كاملاً مع مساحة زخرفية أكبر
    try:
        arabic_font, _ = _fit_font_size(draw, get_smart_font_path("arabic", display_text), [display_text], 48, 64, 64)
    except:
        arabic_font = font
    
    # إعادة حساب الموقع
    try:
        bbox = draw.textbbox((0, 0), display_text, font=arabic_font)
    except:
        bbox = (0, 0, ww, hh)
    
    new_ww = bbox[2] - bbox[0]
    new_hh = bbox[3] - bbox[1]
    new_x, new_y = (100 - new_ww) / 2, (100 - new_hh) / 2
    
    # خلفية زخرفية خلف النص
    bg_color = (255, 250, 240, 80)  # لون عاجي فاتح
    draw.rounded_rectangle(
        [new_x - 10, new_y - 10, new_x + new_ww + 10, new_y + new_hh + 10],
        radius=15,
        fill=bg_color
    )
    
    # النص مع تأثير ذهبي
    gold_colors = [
        (255, 215, 0, 255),  # ذهبي
        (255, 255, 200, 200),  # ذهبي فاتح
        (205, 175, 0, 180)  # ذهبي داكن
    ]
    
    for i, color in enumerate(gold_colors):
        offset = i * 0.8
        draw.text((new_x + offset, new_y + offset), display_text, font=arabic_font, fill=color)
    
    # زخارف عربية معقدة
    ornament_colors = [(139, 69, 19, 200), (210, 105, 30, 180), (255, 215, 0, 150)]
    
    # رسم أنماط عربية حول النص
    pattern_size = 6
    pattern_spacing = 8
    
    # الأعلى
    for i in range(0, int(new_ww + 20), pattern_spacing):
        px = new_x - 10 + i
        py = new_y - 10
        if px < new_x + new_ww + 10:
            draw.rectangle([px, py, px+pattern_size, py+pattern_size], fill=ornament_colors[i%3])
    
    # الأسفل
    for i in range(0, int(new_ww + 20), pattern_spacing):
        px = new_x - 10 + i
        py = new_y + new_hh + 10 - pattern_size
        if px < new_x + new_ww + 10:
            draw.rectangle([px, py, px+pattern_size, py+pattern_size], fill=ornament_colors[(i+1)%3])
    
    # الجانب الأيسر
    for i in range(0, int(new_hh + 20), pattern_spacing):
        px = new_x - 10
        py = new_y - 10 + i
        if py < new_y + new_hh + 10:
            draw.rectangle([px, py, px+pattern_size, py+pattern_size], fill=ornament_colors[(i+2)%3])
    
    # الجانب الأيمن
    for i in range(0, int(new_hh + 20), pattern_spacing):
        px = new_x + new_ww + 10 - pattern_size
        py = new_y - 10 + i
        if py < new_y + new_hh + 10:
            draw.rectangle([px, py, px+pattern_size, py+pattern_size], fill=ornament_colors[i%3])
    
    return result

def apply_english_ornament_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                                x: int, y: int, ww: int, hh: int, fill_color: tuple) -> Image.Image:
    """تطبيق تأثير الزخرفة الإنجليزية المتقدمة"""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    
    # حجم خط كبير جداً - يُضبط تلقائياً ليتسع النص كاملاً مع مساحة زخرفية أكبر
    try:
        ornament_font, _ = _fit_font_size(draw, get_smart_font_path("english_modern", text), [text], 50, 64, 64)
    except:
        ornament_font = font
    
    # إعادة حساب الموقع
    try:
        bbox = draw.textbbox((0, 0), text, font=ornament_font)
    except:
        bbox = (0, 0, ww, hh)
    
    new_ww = bbox[2] - bbox[0]
    new_hh = bbox[3] - bbox[1]
    new_x, new_y = (100 - new_ww) / 2, (100 - new_hh) / 2
    
    # خلفية فاخرة
    bg_gradient = Image.new("RGBA", (100, 100), (240, 240, 240, 60))
    result = Image.alpha_composite(result, bg_gradient)
    draw = ImageDraw.Draw(result)
    
    # تأثير نص بلاتيني (فضي/ذهبي)
    metallic_colors = [
        (192, 192, 192, 255),  # فضي
        (255, 255, 255, 200),  # أبيض لامع
        (150, 150, 150, 180),  # رمادي
        (255, 215, 0, 150)  # ذهبي
    ]
    
    # رسم طبقات متعددة لتأثير المعدن
    for i, color in enumerate(metallic_colors):
        offset_x = random.uniform(-0.5, 0.5) * i
        offset_y = random.uniform(-0.5, 0.5) * i
        draw.text((new_x + offset_x, new_y + offset_y), text, font=ornament_font, fill=color)
    
    # إطار ملكي فاخر
    royal_colors = [(139, 69, 19, 220), (255, 215, 0, 180), (192, 192, 192, 200)]
    
    # إطار خارجي سميك
    for i in range(3):
        frame_color = royal_colors[i]
        frame_size = 8 - i*2
        draw.rounded_rectangle(
            [new_x - frame_size, new_y - frame_size, 
             new_x + new_ww + frame_size, new_y + new_hh + frame_size],
            radius=12 - i*2,
            outline=frame_color,
            width=2
        )
    
    # تيجان في الزوايا
    crown_color = (255, 215, 0, 220)
    crown_size = 6
    
    crowns = [
        # الزاوية العلوية اليسرى
        [(new_x - 8, new_y - 8), (new_x - 8 + crown_size, new_y - 8), 
         (new_x - 8 + crown_size//2, new_y - 8 - crown_size//2)],
        # الزاوية العلوية اليمنى
        [(new_x + new_ww + 8 - crown_size, new_y - 8), (new_x + new_ww + 8, new_y - 8),
         (new_x + new_ww + 8 - crown_size//2, new_y - 8 - crown_size//2)],
        # الزاوية السفلية اليسرى
        [(new_x - 8, new_y + new_hh + 8 - crown_size), (new_x - 8 + crown_size, new_y + new_hh + 8 - crown_size),
         (new_x - 8 + crown_size//2, new_y + new_hh + 8 + crown_size//2)],
        # الزاوية السفلية اليمنى
        [(new_x + new_ww + 8 - crown_size, new_y + new_hh + 8 - crown_size),
         (new_x + new_ww + 8, new_y + new_hh + 8 - crown_size),
         (new_x + new_ww + 8 - crown_size//2, new_y + new_hh + 8 + crown_size//2)]
    ]
    
    for crown in crowns:
        draw.polygon(crown, fill=crown_color)
    
    # أحجار كريمة زائفة
    gem_colors = [(255, 0, 0, 180), (0, 0, 255, 180), (0, 255, 0, 180), (255, 255, 0, 180)]
    
    for i in range(4):
        gem_x = new_x + (i + 1) * (new_ww // 5)
        for j in range(2):
            gem_y = new_y - 12 if j == 0 else new_y + new_hh + 12
            # رسم أحجار كريمة
            draw.ellipse([gem_x-3, gem_y-3, gem_x+3, gem_y+3], fill=gem_colors[i])
            draw.ellipse([gem_x-1, gem_y-1, gem_x+1, gem_y+1], fill=(255, 255, 255, 200))
    
    return result

# ========== Advanced 3D Effects ==========
def apply_3d_building_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont, 
                           x: int, y: int, ww: int, hh: int, fill_color: tuple) -> Image.Image:
    """تطبيق تأثير المبني 3D متطور"""
    # إنشاء صورة جديدة
    result = img.copy()
    draw = ImageDraw.Draw(result)
    
    # إنشاء تأثير عمق 3D
    depth = 8
    shadow_color = (0, 0, 0, 100)
    highlight_color = (255, 255, 255, 80)
    
    # رسم الظل للعمق
    for i in range(depth, 0, -1):
        shadow_color = (0, 0, 0, 50 + i*10)
        draw.text((x + i, y + i), text, font=font, fill=shadow_color)
    
    # رسم النص الأساسي
    _draw_text_maybe_split(draw, (x, y), text, font, fill_color)
    
    # إضافة إضاءة عالية
    draw.text((x - 1, y - 1), text, font=font, fill=highlight_color)
    
    # إضافة تفاصيل المبني (نوافذ)
    window_color = (200, 200, 255, 120)
    window_size = 3
    spacing = 8
    
    # حساب مواقع النوافذ
    start_x = x + 5
    start_y = y + hh + 5
    
    # رسم النوافذ على طول النص
    for i in range(0, ww, spacing):
        for j in range(0, depth, spacing):
            window_x = start_x + i
            window_y = start_y + j
            if window_x < x + ww and window_y < y + hh + depth:
                draw.rectangle(
                    [window_x, window_y, window_x + window_size, window_y + window_size],
                    fill=window_color
                )
    
    return result

def apply_3d_crystal_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                          x: int, y: int, fill_color: tuple) -> Image.Image:
    """تطبيق تأثير الكريستال 3D"""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    
    # ألوان متعددة للكريستال
    crystal_colors = [
        (255, 255, 255, 200),  # أبيض
        (200, 255, 255, 150),  # أزرق فاتح
        (255, 200, 255, 150),  # وردي فاتح
        (255, 255, 200, 150),  # أصفر فاتح
    ]
    
    # رسم طبقات متعددة مع تحولات طفيفة
    for i, color in enumerate(crystal_colors):
        offset = i * 0.5
        draw.text((x + offset, y + offset), text, font=font, fill=color)
    
    # النص الأساسي
    _draw_text_maybe_split(draw, (x, y), text, font, fill_color)
    
    return result

def apply_water_reflection_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                                x: int, y: int, ww: int, hh: int, fill_color: tuple) -> Image.Image:
    """تطبيق تأثير الانعكاس المائي"""
    # إنشاء صورة أكبر للانعكاس
    reflection_height = hh // 2
    result = Image.new("RGBA", (100, 100 + reflection_height), (0, 0, 0, 0))
    
    # نسخ الصورة الأصلية
    result.paste(img, (0, 0))
    
    # إنشاء انعكاس
    reflection = img.copy()
    
    # قلب الانعكاس رأساً على عقب
    reflection = reflection.transpose(Image.FLIP_TOP_BOTTOM)
    
    # تطبيق تأثير الشفافية التدريجية
    alpha = reflection.split()[3]
    alpha_data = alpha.load()
    
    for i in range(reflection_height):
        alpha_value = int(255 * (1 - i / reflection_height))
        for j in range(100):
            if y + hh + i < 100:
                alpha_data[j, i] = alpha_value
    
    # لصق الانعكاس
    result.paste(reflection, (0, 100), reflection)
    
    # قص الصورة إلى الحجم الأصلي
    result = result.crop((0, 0, 100, 100))
    
    return result

def apply_metal_3d_effect(img: Image.Image, text: str, font: ImageFont.FreeTypeFont,
                         x: int, y: int, fill_color: tuple) -> Image.Image:
    """تطبيق تأثير المعدن 3D"""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    
    # ألوان المعدن
    metal_colors = [
        (220, 220, 220, 255),  # فضي فاتح
        (180, 180, 180, 200),  # فضي متوسط
        (100, 100, 100, 150),  # رمادي داكن
        (50, 50, 50, 100),     # أسود
    ]
    
    # رسم تأثير المعدن المتدرج
    for i in range(len(metal_colors)):
        color = metal_colors[i]
        offset = i * 0.7
        draw.text((x + offset, y + offset), text, font=font, fill=color)
    
    # النص الأساسي
    _draw_text_maybe_split(draw, (x, y), text, font, fill_color)
    
    return result

CANVAS_SIZE = 100
CANVAS_MARGIN = 8  # هامش أمان حتى لا يُقص النص عند حواف الاستيكر
MIN_FONT_SIZE = 12


def _fit_font_size(draw: ImageDraw.ImageDraw, font_path: str, texts: List[str],
                    start_size: int, max_width: float, max_height: float,
                    min_size: int = MIN_FONT_SIZE):
    """
    يقلّل حجم الخط تدريجياً حتى يتسع كل نص فى texts داخل الأبعاد المتاحة،
    لمنع قص النص (المشكلة الأساسية اللى بترجّع كلام ناقص فى الاستيكرات).
    يرجع (font, size) بعد إيجاد أفضل حجم يناسب المساحة.
    """
    def _load_font_safely(path: str, sz: int):
        """
        يحاول تحميل الخط المطلوب، ولو فشل (الملف مش موجود فعلاً) يدور على
        أي خط حقيقي شغال على السيرفر بدل ما يرجع لـ load_default() البدائي
        اللي مقاسه ثابت صغير وبيطلع استيكر غلط ومش مفهوم.
        """
        try:
            return ImageFont.truetype(path, sz)
        except Exception:
            pass
        # حاول أي خط تاني حقيقي موجود على السيرفر
        backup_path = _find_any_installed_font()
        if backup_path:
            try:
                return ImageFont.truetype(backup_path, sz)
            except Exception:
                pass
        return ImageFont.load_default()

    size = start_size
    while size >= min_size:
        font = _load_font_safely(font_path, size)

        fits = True
        for t in texts:
            if not t:
                continue
            try:
                bbox = draw.textbbox((0, 0), t, font=font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
            except Exception:
                w = len(t) * size * 0.6
                h = size
            if w > max_width or h > max_height:
                fits = False
                break

        if fits:
            return font, size
        size -= 2

    # لو ما لقيناش حجم مناسب، نرجع أصغر حجم مسموح به كحل أخير
    font = _load_font_safely(font_path, min_size)
    return font, min_size


# ========== Create sticker image for two lines ==========
def create_sticker_image(text: str, style: str, color: str, font_type: str, 
                        effects: List[str] = None, emoji: str = "😎", 
                        text_arrangement: str = "one_line") -> Image.Image:
    """إنشاء صورة استيكر واحدة - تدعم سطر واحد أو سطرين"""
    if effects is None:
        effects = []
    
    img = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # اختيار حجم الخط الابتدائى (سيتم ضبطه تلقائياً بعد ذلك ليتناسب مع النص كاملاً)
    if style in ["style_arabic_calligraphy", "style_arabic_pattern", 
                 "style_arabic_ornament", "style_english_fancy", 
                 "style_english_pattern", "style_english_ornament"]:
        # أنماط الزخرفة تحتاج خطاً أكبر
        font_size = 46 if len(text) < 8 else 40
    elif text_arrangement == "two_lines":
        font_size = 28
    else:
        font_size = 40  # زيادة حجم الخط العام
        
    if font_type in ["impact", "bold"]:
        font_size = min(font_size - 5, 32) if text_arrangement == "two_lines" else 36
    elif font_type in ["comic", "script"]:
        font_size = min(font_size - 3, 30) if text_arrangement == "two_lines" else 34
    
    # إعادة تشكيل النص العربي (يتخطى أي نص مزخرف بالفعل ويتركه كما هو)
    display_text = smart_reshape_text(text)
    
    try:
        font_path = get_smart_font_path(font_type, display_text)
    except Exception as e:
        print(f"Error loading font path: {e}")
        font_path = None
    
    fill_color = color_rgb(color)
    
    # تعريف المتغيرات الأساسية
    x, y, ww, hh = 0, 0, 0, 0
    max_w = CANVAS_SIZE - CANVAS_MARGIN * 2
    max_h = CANVAS_SIZE - CANVAS_MARGIN * 2
    
    if text_arrangement == "two_lines":
        # تقسيم النص إلى سطرين بشكل متوازن (لتقليل طول أطول سطر ومنع القص)
        if " " in text.strip():
            words = text.strip().split(" ")
            best_split = 1
            best_diff = None
            running = ""
            for i in range(1, len(words)):
                left = " ".join(words[:i])
                right = " ".join(words[i:])
                diff = abs(len(left) - len(right))
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_split = i
            line1 = " ".join(words[:best_split]).strip()
            line2 = " ".join(words[best_split:]).strip()
        else:
            mid = len(text) // 2
            line1 = text[:mid]
            line2 = text[mid:]
        
        # إعادة تشكيل النص العربي للسطرين (يتخطى أي نص مزخرف بالفعل ويتركه كما هو)
        display_line1 = smart_reshape_text(line1)
        display_line2 = smart_reshape_text(line2)
        
        # ضبط حجم الخط تلقائياً بحيث يتسع السطران كاملين بدون قص
        if font_path:
            font, font_size = _fit_font_size(
                draw, font_path, [display_line1, display_line2],
                font_size, max_w, (max_h - 10) / 2
            )
        else:
            font = ImageFont.load_default()
        
        # حساب أبعاد السطرين
        try:
            bbox1 = draw.textbbox((0, 0), display_line1, font=font)
            bbox2 = draw.textbbox((0, 0), display_line2, font=font)
        except:
            bbox1 = (0, 0, len(display_line1) * font_size, font_size)
            bbox2 = (0, 0, len(display_line2) * font_size, font_size)
        
        ww1 = bbox1[2] - bbox1[0]
        hh1 = bbox1[3] - bbox1[1]
        ww2 = bbox2[2] - bbox2[0]
        hh2 = bbox2[3] - bbox2[1]
        
        # حساب المواضع
        max_width = max(ww1, ww2)
        total_height = hh1 + hh2 + 10
        
        x1 = (100 - ww1) / 2
        y1 = (100 - total_height) / 2
        x2 = (100 - ww2) / 2
        y2 = y1 + hh1 + 10
        
        # تخزين أبعاد النص الكلي للتأثيرات اللاحقة
        x = min(x1, x2)
        y = y1
        ww = max(ww1, ww2)
        hh = total_height
        
        # تطبيق الأسلوب على السطرين
        if style == "style_3d" or style == "style_3d_gold":
            # تأثير 3D الذهبي
            for i in range(5, 0, -1):
                shadow_color = (0, 0, 0, 50 + i*10)
                draw.text((x1 + i, y1 + i), display_line1, font=font, fill=shadow_color)
                draw.text((x2 + i, y2 + i), display_line2, font=font, fill=shadow_color)
            
            _draw_text_maybe_split(draw, (x1, y1), display_line1, font, fill_color)
            _draw_text_maybe_split(draw, (x2, y2), display_line2, font, fill_color)
            
            # إضافة بريق ذهبي
            sparkle_color = (255, 255, 200, 150)
            for _ in range(3):
                px1 = random.randint(int(x1), int(x1 + ww1))
                py1 = random.randint(int(y1), int(y1 + hh1))
                px2 = random.randint(int(x2), int(x2 + ww2))
                py2 = random.randint(int(y2), int(y2 + hh2))
                draw.ellipse([px1-1, py1-1, px1+1, py1+1], fill=sparkle_color)
                draw.ellipse([px2-1, py2-1, px2+1, py2+1], fill=sparkle_color)
                
        elif style == "style_3d_building":
            # تأثير المبني 3D
            img = apply_3d_building_effect(img, display_line1, font, x1, y1, ww1, hh1, fill_color)
            img = apply_3d_building_effect(img, display_line2, font, x2, y2, ww2, hh2, fill_color)
            
        elif style == "style_3d_crystal":
            # تأثير الكريستال 3D
            img = apply_3d_crystal_effect(img, display_line1, font, x1, y1, fill_color)
            img = apply_3d_crystal_effect(img, display_line2, font, x2, y2, fill_color)
            
        elif style == "style_metal":
            # تأثير المعدن
            for i in range(3):
                draw.text((x1 + i, y1 + i), display_line1, font=font, fill=(200, 200, 200, 100))
                draw.text((x2 + i, y2 + i), display_line2, font=font, fill=(200, 200, 200, 100))
            _draw_text_maybe_split(draw, (x1, y1), display_line1, font, fill_color)
            _draw_text_maybe_split(draw, (x2, y2), display_line2, font, fill_color)
            
        elif style == "style_neon":
            # تأثير النيون
            for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                neon_color = (255, 255, 255, 100)
                draw.text((x1 + dx, y1 + dy), display_line1, font=font, fill=neon_color)
                draw.text((x2 + dx, y2 + dy), display_line2, font=font, fill=neon_color)
            _draw_text_maybe_split(draw, (x1, y1), display_line1, font, fill_color)
            _draw_text_maybe_split(draw, (x2, y2), display_line2, font, fill_color)
            
        elif style == "style_arabic_calligraphy":
            # تأثير الخط العربي المزخرف - يُرسم كل سطر على حدة لمنع القص أو التراكب
            img = apply_arabic_calligraphy_effect(img, line1, font, x1, y1, ww1, hh1, fill_color, center_y=25, max_h=44)
            img = apply_arabic_calligraphy_effect(img, line2, font, x2, y2, ww2, hh2, fill_color, center_y=75, max_h=44)
            
        elif style == "style_english_fancy":
            # تأثير الزخرفة الإنجليزية - يُرسم كل سطر على حدة لمنع القص أو التراكب
            img = apply_english_fancy_effect(img, line1, font, x1, y1, ww1, hh1, fill_color, center_y=25, max_h=44)
            img = apply_english_fancy_effect(img, line2, font, x2, y2, ww2, hh2, fill_color, center_y=75, max_h=44)
            
        elif style == "style_arabic_pattern":
            # تأثير الزخارف العربية - يُرسم كل سطر على حدة لمنع القص أو التراكب
            img = apply_arabic_pattern_effect(img, line1, font, x1, y1, ww1, hh1, fill_color, center_y=25, max_h=44)
            img = apply_arabic_pattern_effect(img, line2, font, x2, y2, ww2, hh2, fill_color, center_y=75, max_h=44)
            
        elif style == "style_english_pattern":
            # تأثير الزخارف الإنجليزية - يُرسم كل سطر على حدة لمنع القص أو التراكب
            img = apply_english_pattern_effect(img, line1, font, x1, y1, ww1, hh1, fill_color, center_y=25, max_h=44)
            img = apply_english_pattern_effect(img, line2, font, x2, y2, ww2, hh2, fill_color, center_y=75, max_h=44)
            
        else:
            # الأسلوب العادي
            _draw_text_maybe_split(draw, (x1, y1), display_line1, font, fill_color)
            _draw_text_maybe_split(draw, (x2, y2), display_line2, font, fill_color)
            
    else:
        # سطر واحد - ضبط حجم الخط تلقائياً بحيث يتسع النص كاملاً بدون قص
        if font_path:
            font, font_size = _fit_font_size(
                draw, font_path, [display_text], font_size, max_w, max_h
            )
        else:
            font = ImageFont.load_default()
        
        try:
            bbox = draw.textbbox((0, 0), display_text, font=font)
        except:
            bbox = (0, 0, len(display_text) * font_size, font_size)
        
        ww = bbox[2] - bbox[0]
        hh = bbox[3] - bbox[1]
        x, y = (100 - ww) / 2, (100 - hh) / 2
        
        # تطبيق الأسلوب
        if style == "style_3d" or style == "style_3d_gold":
            # تأثير 3D الذهبي
            for i in range(5, 0, -1):
                shadow_color = (0, 0, 0, 50 + i*10)
                draw.text((x + i, y + i), display_text, font=font, fill=shadow_color)
            
            _draw_text_maybe_split(draw, (x, y), display_text, font, fill_color)
            
            # إضافة بريق ذهبي
            sparkle_color = (255, 255, 200, 150)
            for _ in range(5):
                px = random.randint(int(x), int(x + ww))
                py = random.randint(int(y), int(y + hh))
                draw.ellipse([px-1, py-1, px+1, py+1], fill=sparkle_color)
                
        elif style == "style_3d_building":
            # تأثير المبني 3D
            img = apply_3d_building_effect(img, display_text, font, x, y, ww, hh, fill_color)
            
        elif style == "style_3d_crystal":
            # تأثير الكريستال 3D
            img = apply_3d_crystal_effect(img, display_text, font, x, y, fill_color)
            
        elif style == "style_3d_metal":
            # تأثير المعدن 3D
            img = apply_metal_3d_effect(img, display_text, font, x, y, fill_color)
            
        elif style == "style_cartoon":
            # تأثير الكرتون
            draw.text((x - 1, y - 1), display_text, font=font, fill=(0, 0, 0, 150))
            _draw_text_maybe_split(draw, (x, y), display_text, font, fill_color)
            
        elif style == "style_metal":
            # تأثير المعدن
            for i in range(3):
                draw.text((x + i, y + i), display_text, font=font, fill=(200, 200, 200, 100))
            _draw_text_maybe_split(draw, (x, y), display_text, font, fill_color)
            
        elif style == "style_neon":
            # تأثير النيون
            for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                neon_color = (255, 255, 255, 100)
                draw.text((x + dx, y + dy), display_text, font=font, fill=neon_color)
            _draw_text_maybe_split(draw, (x, y), display_text, font, fill_color)
            
        elif style == "style_gradient":
            # تأثير التدرج اللوني
            # (بنستخدم لون واحد ممثل حتى لو اللون المختار "لون مشترك" لتفادي خطأ الضرب فى تيوبل)
            _solid_bg = _solid_fill_color(fill_color)
            for i in range(100):
                r = int(_solid_bg[0] * (i / 100))
                g = int(_solid_bg[1] * (i / 100))
                b = int(_solid_bg[2] * (i / 100))
                draw.line([(0, i), (100, i)], fill=(r, g, b, 255))
            draw.text((x, y), display_text, font=font, fill=(255, 255, 255, 255))
            
        elif style == "style_arabic_calligraphy":
            # تأثير الخط العربي المزخرف
            img = apply_arabic_calligraphy_effect(img, text, font, x, y, ww, hh, fill_color)
            
        elif style == "style_english_fancy":
            # تأثير الزخرفة الإنجليزية
            img = apply_english_fancy_effect(img, text, font, x, y, ww, hh, fill_color)
            
        elif style == "style_arabic_pattern":
            # تأثير الزخارف العربية
            img = apply_arabic_pattern_effect(img, text, font, x, y, ww, hh, fill_color)
            
        elif style == "style_english_pattern":
            # تأثير الزخارف الإنجليزية
            img = apply_english_pattern_effect(img, text, font, x, y, ww, hh, fill_color)
            
        elif style == "style_arabic":
            # الخط العربي الفخم - نفس منطق ضبط الحجم لمنع قص النص
            try:
                arabic_path = get_smart_font_path("arabic", display_text)
                arabic_font, _ = _fit_font_size(
                    draw, arabic_path, [display_text], 42, max_w, max_h
                )
                bbox = draw.textbbox((0, 0), display_text, font=arabic_font)
                ww = bbox[2] - bbox[0]
                hh = bbox[3] - bbox[1]
                x, y = (100 - ww) / 2, (100 - hh) / 2
                
                for i in range(3, 0, -1):
                    draw.text((x + i, y + i), display_text, font=arabic_font, fill=(0, 0, 0, 50))
                _draw_text_maybe_split(draw, (x, y), display_text, arabic_font, fill_color)
            except:
                _draw_text_maybe_split(draw, (x, y), display_text, font, fill_color)
            
        else:
            # الأسلوب العادي
            _draw_text_maybe_split(draw, (x, y), display_text, font, fill_color)
    
    # تجهيز قائمة أجزاء النص (سطر واحد أو سطرين) لاستخدامها فى التأثيرات الإضافية
    # حتى لا يتم رسم النص الكامل كسطر واحد فوق تصميم مقسّم لسطرين (كان يسبب قص/تراكب)
    if text_arrangement == "two_lines":
        _draw_segments = [(display_line1, x1, y1), (display_line2, x2, y2)]
    else:
        _draw_segments = [(display_text, x, y)]

    # تطبيق التأثيرات الإضافية
    for effect in effects:
        if effect == "effect_arabic_ornament":
            # تأثير الزخرفة العربية المتقدمة
            try:
                img = apply_arabic_ornament_effect(img, text, font, x, y, ww, hh, fill_color)
            except Exception as e:
                print(f"Error applying arabic ornament: {e}")
                pass
                
        elif effect == "effect_english_ornament":
            # تأثير الزخرفة الإنجليزية المتقدمة
            try:
                img = apply_english_ornament_effect(img, text, font, x, y, ww, hh, fill_color)
            except Exception as e:
                print(f"Error applying english ornament: {e}")
                pass
            
        elif effect == "effect_water":
            # تأثير الانعكاس المائي
            try:
                img = apply_water_reflection_effect(img, text, font, x, y, ww, hh, fill_color)
            except Exception as e:
                print(f"Error applying water reflection: {e}")
                pass
            
        elif effect == "effect_3d_depth":
            # تأثير العمق 3D
            try:
                depth_img = img.copy()
                depth_draw = ImageDraw.Draw(depth_img)
                for i in range(3, 0, -1):
                    depth_color = (0, 0, 0, 30 * i)
                    for seg_text, seg_x, seg_y in _draw_segments:
                        depth_draw.text((seg_x + i*2, seg_y + i*2), seg_text, font=font, fill=depth_color)
                img = Image.alpha_composite(img, depth_img)
            except:
                pass
            
        elif effect == "effect_glossy":
            # تأثير اللمعان
            try:
                glossy_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
                glossy_draw = ImageDraw.Draw(glossy_img)
                
                # إضافة إضاءة علوية
                for i in range(10):
                    alpha = 100 - i * 10
                    glossy_color = (255, 255, 255, alpha)
                    glossy_draw.ellipse(
                        [x + ww//4, y - 5 + i, x + ww*3//4, y + 5 + i],
                        fill=glossy_color
                    )
                img = Image.alpha_composite(img, glossy_img)
            except:
                pass
            
        elif effect == "effect_shadow":
            # تأثير الظل
            try:
                shadow_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
                shadow_draw = ImageDraw.Draw(shadow_img)
                for seg_text, seg_x, seg_y in _draw_segments:
                    shadow_draw.text((seg_x + 2, seg_y + 2), seg_text, font=font, fill=(0, 0, 0, 150))
                img = Image.alpha_composite(img, shadow_img)
            except:
                pass
            
        elif effect == "effect_glow":
            # تأثير الإضاءة
            try:
                glow_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
                glow_draw = ImageDraw.Draw(glow_img)
                for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
                    for seg_text, seg_x, seg_y in _draw_segments:
                        glow_draw.text((seg_x + dx, seg_y + dy), seg_text, font=font, fill=(255, 255, 0, 80))
                img = Image.alpha_composite(img, glow_img)
            except:
                pass
            
        elif effect == "effect_frame":
            # تأثير الإطار
            try:
                draw.rectangle([(5, 5), (95, 95)], outline=fill_color, width=2)
            except:
                pass
            
        elif effect == "effect_gold_leaf":
            # تأثير الورق الذهبي
            try:
                gold_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
                gold_draw = ImageDraw.Draw(gold_img)
                
                gold_colors = [
                    (255, 215, 0, 200),
                    (255, 255, 100, 150),
                    (205, 175, 0, 100)
                ]
                
                for i, color in enumerate(gold_colors):
                    offset = i * 0.5
                    for seg_text, seg_x, seg_y in _draw_segments:
                        gold_draw.text((seg_x + offset, seg_y + offset), seg_text, font=font, fill=color)
                
                img = Image.alpha_composite(img, gold_img)
            except:
                pass
            
        elif effect == "effect_crystal_shine":
            # تأثير بريق الكريستال
            try:
                shine_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
                shine_draw = ImageDraw.Draw(shine_img)
                
                # نقاط بريق عشوائية
                for _ in range(15):
                    px = random.randint(int(x), int(x + ww))
                    py = random.randint(int(y), int(y + hh))
                    size = random.randint(1, 3)
                    alpha = random.randint(100, 200)
                    shine_color = (255, 255, 255, alpha)
                    shine_draw.ellipse([px-size, py-size, px+size, py+size], fill=shine_color)
                
                img = Image.alpha_composite(img, shine_img)
            except:
                pass
            
        elif effect == "effect_royal_frame":
            # تأثير الإطار الملكي
            try:
                frame_colors = [(139, 69, 19, 220), (255, 215, 0, 180)]
                
                # إطار خارجي
                draw.rounded_rectangle(
                    [x - 8, y - 8, x + ww + 8, y + hh + 8],
                    radius=12,
                    outline=frame_colors[0],
                    width=3
                )
                
                # إطار داخلي
                draw.rounded_rectangle(
                    [x - 4, y - 4, x + ww + 4, y + hh + 4],
                    radius=8,
                    outline=frame_colors[1],
                    width=2
                )
            except:
                pass
    
    return img

# ========== Start / Language ==========
WELCOME_IMAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "welcome.jpg")

async def smart_edit(q, text, reply_markup=None):
    """
    يعدّل رسالة الكولباك بأمان بغض النظر عن نوعها:
    - لو الرسالة نص عادي -> يعدل النص (زي المعتاد).
    - لو الرسالة صورة (زي شاشة الترحيب بصورة البوت) -> يعدل الكابشن بدلاً من النص،
      لأن تليجرام مابيسمحش بتعديل نص رسالة فيها صورة عن طريق edit_message_text
      (بيرجع خطأ "There is no text in the message to edit").
    """
    if q.message is not None and getattr(q.message, "photo", None):
        await q.edit_message_caption(caption=text, reply_markup=reply_markup)
    else:
        await q.edit_message_text(text, reply_markup=reply_markup)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """بدء البوت"""
    user = update.effective_user
    
    save_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    kb = [
        [IKB("🇪🇬 العربية", callback_data="lang_ar", style="primary"),
         IKB("🇬🇧 English", callback_data="lang_en", style="success")]
    ]
    
    welcome_text = "🎨 مرحباً! أهلاً بك في بوت إنشاء الاستيكرات المميزة 👋\n\n"
    welcome_text += "✨ المميزات:\n"
    welcome_text += "• إنشاء استيكرات نصية بتأثيرات 3D متطورة\n"
    welcome_text += "• زخارف عربية وإنجليزية فاخرة\n"
    welcome_text += "• خطوط عربية مزخرفة بأنواع مختلفة\n"
    welcome_text += "• دعم التأثيرات المتعددة والزخارف الفاخرة\n"
    welcome_text += "• إنشاء رموز مميزة (Custom Emojis)\n\n"
    welcome_text += "🎯 اختر لغتك / Choose your language:"
    
    # نعرض صورة البوت فوق، والنص كابشن تحتها، وأزرار اللغة تحت الصورة
    # (لو الصورة مش موجودة فى المسار، نرجع تلقائياً لرسالة نصية عادية عشان البوت مايقفش)
    if os.path.exists(WELCOME_IMAGE_PATH):
        with open(WELCOME_IMAGE_PATH, "rb") as photo_file:
            await update.message.reply_photo(
                photo=photo_file,
                caption=welcome_text,
                reply_markup=InlineKeyboardMarkup(kb)
            )
    else:
        await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(kb))

async def set_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تحديد لغة المستخدم"""
    q = update.callback_query
    await q.answer()
    
    lang = q.data.split("_")[1]
    user_id = q.from_user.id
    
    update_user_lang(user_id, lang)
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    USER_DATA[user_id]["lang"] = lang
    
    if not await is_member(user_id, ctx):
        kb = [[IKB(LANGS[lang]["check"], callback_data="check_sub", style="primary")]]
        await smart_edit(q, LANGS[lang]["member"], reply_markup=InlineKeyboardMarkup(kb))
        return
    
    await main_menu(q, ctx, lang)

async def main_menu(q, ctx: ContextTypes.DEFAULT_TYPE, lang: str = None, user_id: int = None):
    """القائمة الرئيسية"""
    if not user_id:
        user_id = q.from_user.id
    
    if not lang:
        lang = USER_DATA.get(user_id, {}).get("lang", "ar")
    
    if "lang" not in USER_DATA.get(user_id, {}):
        USER_DATA[user_id] = USER_DATA.get(user_id, {})
        USER_DATA[user_id]["lang"] = lang
    
    # التحقق من حالة اشتراك المستخدم
    is_user_premium = is_premium(user_id)
    sub_info = get_user_subscription_info(user_id)
    
    # بناء الرسالة مع معلومات الاشتراك والاستخدام
    start_text = LANGS[lang]["start"]
    
    if SUBSCRIPTION_ENABLED:
        if is_user_premium:
            start_text += f"\n\n⭐ حالتك: مشترك مميز"
            if sub_info.get("days_left"):
                start_text += f"\n⏳ الأيام المتبقية: {sub_info['days_left']}"
        else:
            today_usage = get_today_usage(user_id)
            remaining = max(0, 3 - today_usage)
            start_text += f"\n\n📊 الاستخدام اليومي: {today_usage}/3"
            start_text += f"\n🎯 باقي لك اليوم: {remaining} مرات"
            start_text += f"\n💡 للاستخدام غير المحدود: اشترك الآن ⭐"
    
    # لوحة أزرار منظمة
    kb = [
        [IKB(LANGS[lang]["text"], callback_data="send_text", style="success")],
        [IKB(LANGS[lang]["photo"], callback_data="send_photo", style="primary")],
        [IKB(LANGS[lang]["video"], callback_data="send_video", style="success")],
        [IKB(LANGS[lang]["animated"], callback_data="send_animated", style="primary")],
        [IKB(LANGS[lang]["regular_sticker"], callback_data="send_regular_sticker", style="success")],
        [IKB(LANGS[lang]["sticker_to_emoji"], callback_data="sticker_to_emoji", style="primary")],
        [IKB(LANGS[lang]["my_stickers"], callback_data="my_stickers", style="success")]
    ]
    
    if SUBSCRIPTION_ENABLED:
        if is_user_premium:
            # عرض زر مميز للمشتركين
            kb.append([IKB("⭐ عضويتك المميزة", callback_data="my_subscription", style="primary")])
        else:
            # زر اشتراك عادي
            kb.append([IKB(LANGS[lang]["subscribe"], callback_data="subscribe", style="success")])
    
    # صف واحد للغة والمطور
    lang_dev_row = []
    lang_dev_row.append(IKB(LANGS[lang]["lang"], callback_data="change_lang", style="primary"))
    lang_dev_row.append(IKB(LANGS[lang]["developer"], url=f"t.me/{OWNER_USER}", style="success"))
    kb.append(lang_dev_row)
    
    if user_id in ADMIN_IDS:
        kb.append([IKB(LANGS[lang]["admin_menu"], callback_data="admin_menu", style="primary")])
    
    await smart_edit(q, start_text, reply_markup=InlineKeyboardMarkup(kb))

async def check_sub(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """التحقق من الاشتراك"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if not await is_member(user_id, ctx):
        await smart_edit(q, LANGS[lang]["member"])
        return
    
    await main_menu(q, ctx, lang)

async def change_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تغيير اللغة"""
    q = update.callback_query
    await q.answer()
    
    kb = [
        [IKB("🇪🇬 العربية", callback_data="lang_ar", style="success"),
         IKB("🇬🇧 English", callback_data="lang_en", style="primary")]
    ]
    
    await smart_edit(q, "🌐 Choose your language / اختر لغتك:", reply_markup=InlineKeyboardMarkup(kb))

async def return_to_main_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE, lang: str, user_id: int):
    """العودة للقائمة الرئيسية"""
    try:
        is_user_premium = is_premium(user_id)
        sub_info = get_user_subscription_info(user_id)
        
        start_text = LANGS[lang]["start"]
        
        if SUBSCRIPTION_ENABLED:
            if is_user_premium:
                start_text += f"\n\n⭐ حالتك: مشترك مميز"
                if sub_info.get("days_left"):
                    start_text += f"\n⏳ الأيام المتبقية: {sub_info['days_left']}"
            else:
                today_usage = get_today_usage(user_id)
                remaining = max(0, 3 - today_usage)
                start_text += f"\n\n📊 الاستخدام اليومي: {today_usage}/3"
                start_text += f"\n🎯 باقي لك اليوم: {remaining} مرات"
                start_text += f"\n💡 للاستخدام غير المحدود: اشترك الآن ⭐"
        
        kb = [
            [IKB(LANGS[lang]["text"], callback_data="send_text", style="success")],
            [IKB(LANGS[lang]["photo"], callback_data="send_photo", style="primary")],
            [IKB(LANGS[lang]["video"], callback_data="send_video", style="success")],
            [IKB(LANGS[lang]["animated"], callback_data="send_animated", style="primary")],
            [IKB(LANGS[lang]["sticker_to_emoji"], callback_data="sticker_to_emoji", style="success")],
            [IKB(LANGS[lang]["my_stickers"], callback_data="my_stickers", style="primary")]
        ]
        
        if SUBSCRIPTION_ENABLED:
            if is_user_premium:
                kb.append([IKB("⭐ عضويتك المميزة", callback_data="my_subscription", style="success")])
            else:
                kb.append([IKB(LANGS[lang]["subscribe"], callback_data="subscribe", style="primary")])
        
        # صف واحد للغة والمطور
        lang_dev_row = []
        lang_dev_row.append(IKB(LANGS[lang]["lang"], callback_data="change_lang", style="success"))
        lang_dev_row.append(IKB(LANGS[lang]["developer"], url=f"t.me/{OWNER_USER}", style="primary"))
        kb.append(lang_dev_row)
        
        if user_id in ADMIN_IDS:
            kb.append([IKB(LANGS[lang]["admin_menu"], callback_data="admin_menu", style="success")])
        
        await ctx.bot.send_message(
            chat_id=user_id,
            text=start_text,
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except Exception as e:
        print(f"Error returning to main menu: {e}")

# ========== My Stickers Menu ==========
async def my_stickers_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """قائمة استيكراتي"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    # الحصول على استيكرات المستخدم
    stickers = get_user_stickers(user_id, limit=20)
    
    if not stickers:
        kb = [[IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]]
        await smart_edit(q, LANGS[lang]["no_stickers"], reply_markup=InlineKeyboardMarkup(kb))
        return
    
    # تقسيم الاستيكرات إلى صفحات
    stickers_per_page = 5
    pages = [stickers[i:i+stickers_per_page] for i in range(0, len(stickers), stickers_per_page)]
    
    # حفظ بيانات الصفحة
    if "sticker_pages" not in ctx.user_data:
        ctx.user_data["sticker_pages"] = {}
    ctx.user_data["sticker_pages"][user_id] = {
        "pages": pages,
        "current_page": 0,
        "total_pages": len(pages)
    }
    
    await show_sticker_page(q, ctx, lang, user_id, 0)

async def show_sticker_page(q, ctx: ContextTypes.DEFAULT_TYPE, lang: str, user_id: int, page_num: int):
    """عرض صفحة من الاستيكرات"""
    pages_data = ctx.user_data.get("sticker_pages", {}).get(user_id)
    if not pages_data:
        await main_menu(q, ctx, lang, user_id)
        return
    
    pages = pages_data["pages"]
    total_pages = pages_data["total_pages"]
    
    if page_num >= total_pages:
        page_num = total_pages - 1
    if page_num < 0:
        page_num = 0
    
    current_page = pages[page_num]
    
    # بناء نص الرسالة
    message_text = f"📁 {LANGS[lang]['my_stickers_title']}\n\n"
    message_text += f"📄 الصفحة {page_num + 1} من {total_pages}\n\n"
    
    for i, (set_name, created_at, title, is_custom_emoji, is_video) in enumerate(current_page):
        time_str = time.strftime("%Y-%m-%d", time.localtime(created_at))
        sticker_title = title if title else f"استيكر {i+1}"
        emoji_type = "✨" if is_custom_emoji else "🎨"
        video_icon = "🎥" if is_video else ""
        message_text += f"{emoji_type}{video_icon} {i+1}. {sticker_title} ({time_str})\n"
    
    # بناء الأزرار
    kb = []
    
    # أزرار الروابط للصفحة الحالية
    for i, (set_name, created_at, title, is_custom_emoji, is_video) in enumerate(current_page):
        row = [
            IKB(f"🔗 {i+1}", url=f"https://t.me/addstickers/{set_name}", style="primary"),
            IKB(f"📋 {i+1}", callback_data=f"copy_{set_name}", style="success")
        ]
        kb.append(row)
    
    # أزرار التنقل بين الصفحات
    nav_buttons = []
    if page_num > 0:
        nav_buttons.append(IKB("◀️", callback_data=f"stickers_page_{page_num-1}", style="primary"))
    
    nav_buttons.append(IKB(f"📄 {page_num+1}/{total_pages}", callback_data="noop", style="success"))
    
    if page_num < total_pages - 1:
        nav_buttons.append(IKB("▶️", callback_data=f"stickers_page_{page_num+1}", style="primary"))
    
    if nav_buttons:
        kb.append(nav_buttons)
    
    # زر العودة
    kb.append([IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")])
    
    # تحديث الرسالة
    try:
        await smart_edit(q, message_text, reply_markup=InlineKeyboardMarkup(kb))
    except:
        # إذا فشل التحديث، أرسل رسالة جديدة
        await ctx.bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(kb)
        )

async def handle_sticker_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة تغيير صفحة الاستيكرات"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    # استخراج رقم الصفحة
    page_num = int(q.data.split("_")[-1])
    
    await show_sticker_page(q, ctx, lang, user_id, page_num)

async def handle_copy_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """نسخ رابط الاستيكر"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    # استخراج اسم الحزمة
    set_name = q.data.replace("copy_", "")
    full_link = f"https://t.me/addstickers/{set_name}"
    
    # إرسال الرسالة مع الرابط للنسخ
    await smart_edit(q, 
        f"📋 رابط الاستيكر:\n\n`{full_link}`\n\n"
        f"🔗 أو افتحه مباشرة:\n{full_link}\n\n"
        f"📌 اضغط على الرابط أعلاه لنسخه"
    )
    
    # زر العودة
    kb = [[IKB(LANGS[lang]["back"], callback_data="my_stickers", style="danger")]]
    await asyncio.sleep(2)
    await ctx.bot.send_message(
        chat_id=q.message.chat_id,
        text="🔙 العودة لقائمة استيكراتك:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ========== إدارة الاشتراكات للأدمن ==========
async def subscription_management(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """قائمة إدارة الاشتراكات"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    kb = [
        [IKB(LANGS[lang]["add_subscription"], callback_data="admin_add_sub", style="success")],
        [IKB(LANGS[lang]["remove_subscription"], callback_data="admin_remove_sub", style="danger")],
        [IKB(LANGS[lang]["view_subscribers"], callback_data="admin_view_subs", style="primary")],
        [IKB(LANGS[lang]["subscription_stats"], callback_data="admin_sub_stats", style="success")],
        [IKB(LANGS[lang]["search_user"], callback_data="admin_search_user", style="primary")],
        [IKB(LANGS[lang]["go_back_admin"], callback_data="admin_menu", style="danger")]
    ]
    
    await smart_edit(q, LANGS[lang]["subscription_management"], reply_markup=InlineKeyboardMarkup(kb))

async def admin_add_subscription(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إضافة اشتراك للمستخدم"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    ctx.user_data["admin_action"] = "add_subscription"
    
    kb = [[IKB(LANGS[lang]["cancel"], callback_data="subscription_management", style="danger")]]
    await smart_edit(q, LANGS[lang]["enter_user_id"], reply_markup=InlineKeyboardMarkup(kb))
    
    return "ADMIN_USER_ID"

async def admin_remove_subscription(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إزالة اشتراك من المستخدم"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    ctx.user_data["admin_action"] = "remove_subscription"
    
    kb = [[IKB(LANGS[lang]["cancel"], callback_data="subscription_management", style="danger")]]
    await smart_edit(q, LANGS[lang]["enter_user_id"], reply_markup=InlineKeyboardMarkup(kb))
    
    return "ADMIN_USER_ID"

async def admin_view_subscribers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عرض جميع المشتركين"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    subscribers = get_all_subscribers()
    
    if not subscribers:
        kb = [[IKB(LANGS[lang]["go_back_admin"], callback_data="subscription_management", style="danger")]]
        await smart_edit(q, LANGS[lang]["no_subscribers"], reply_markup=InlineKeyboardMarkup(kb))
        return
    
    message_text = f"👥 {LANGS[lang]['all_subscribers'].format(count=len(subscribers))}\n\n"
    
    for i, (sub_id, expiry) in enumerate(subscribers[:50], 1):  # عرض أول 50 مشترك فقط
        try:
            user = await ctx.bot.get_chat(sub_id)
            username = f"@{user.username}" if user.username else user.first_name
        except:
            username = f"ID: {sub_id}"
        
        days_left = max(0, (expiry - int(time.time())) // 86400)
        plan = "غير معروف"
        
        # محاولة تحديد الباقة
        for plan_key, plan_info in SUBSCRIPTION_PLANS.items():
            if abs((expiry - int(time.time())) - (plan_info["days"] * 86400)) < 86400 * 5:
                plan = LANGS[lang][f"plan_{plan_key}"] if f"plan_{plan_key}" in LANGS[lang] else plan_key
                break
        
        message_text += f"{i}. {username}\n"
        message_text += f"   📦 {plan}\n"
        message_text += f"   ⏳ {days_left} يوم\n"
        message_text += f"   📅 {time.strftime('%Y-%m-%d', time.localtime(expiry))}\n\n"
    
    kb = [[IKB(LANGS[lang]["go_back_admin"], callback_data="subscription_management", style="danger")]]
    await smart_edit(q, message_text, reply_markup=InlineKeyboardMarkup(kb))

async def admin_subscription_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إحصائيات الاشتراكات"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    stats = get_subscription_stats()
    
    message_text = f"📊 {LANGS[lang]['subscription_stats']}\n\n"
    message_text += f"{LANGS[lang]['stats_total'].format(total=stats['total_active'])}\n\n"
    message_text += f"{LANGS[lang]['stats_by_plan']}\n"
    
    for plan_key, count in stats["plans"].items():
        plan_name = LANGS[lang][f"plan_{plan_key}"] if f"plan_{plan_key}" in LANGS[lang] else plan_key
        message_text += f"  • {plan_name}: {count}\n"
    
    message_text += f"\n{LANGS[lang]['stats_expiring_soon'].format(count=stats['expiring_soon'])}"
    
    kb = [[IKB(LANGS[lang]["go_back_admin"], callback_data="subscription_management", style="danger")]]
    await smart_edit(q, message_text, reply_markup=InlineKeyboardMarkup(kb))

async def admin_search_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """البحث عن مستخدم"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    ctx.user_data["admin_action"] = "search_user"
    
    kb = [[IKB(LANGS[lang]["cancel"], callback_data="subscription_management", style="danger")]]
    await smart_edit(q, LANGS[lang]["enter_user_id"], reply_markup=InlineKeyboardMarkup(kb))
    
    return "ADMIN_USER_ID"

async def handle_admin_user_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة آيدي المستخدم الذي أدخله الأدمن"""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        return ConversationHandler.END
    
    try:
        target_user_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text(LANGS[lang]["user_id_invalid"])
        return "ADMIN_USER_ID"
    
    action = ctx.user_data.get("admin_action")
    
    try:
        target_user = await ctx.bot.get_chat(target_user_id)
        username = f"@{target_user.username}" if target_user.username else target_user.first_name
    except:
        username = f"ID: {target_user_id}"
    
    if action == "search_user":
        sub_info = get_user_subscription_info(target_user_id)
        
        message_text = f"📋 {LANGS[lang]['user_subscription_info']}\n\n"
        message_text += f"👤 {username}\n"
        message_text += f"🆔 {target_user_id}\n\n"
        
        if sub_info["active"]:
            message_text += f"✅ {LANGS[lang]['subscription_active']}\n"
            message_text += f"📦 الباقة: {sub_info['plan']}\n"
            message_text += f"{LANGS[lang]['expiry_date']} {sub_info['expiry_date']}\n"
            message_text += f"{LANGS[lang]['days_remaining']} {sub_info['days_left']}\n"
        else:
            message_text += f"❌ {LANGS[lang]['subscription_expired']}\n"
            if sub_info["expiry"]:
                message_text += f"⏰ آخر انتهاء: {time.strftime('%Y-%m-%d', time.localtime(sub_info['expiry']))}"
        
        kb = [[IKB(LANGS[lang]["go_back_admin"], callback_data="subscription_management", style="danger")]]
        await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(kb))
        
    elif action == "add_subscription":
        ctx.user_data["target_user_id"] = target_user_id
        ctx.user_data["target_username"] = username
        
        kb = []
        for plan_key in SUBSCRIPTION_PLANS:
            plan_name = LANGS[lang][f"plan_{plan_key}"] if f"plan_{plan_key}" in LANGS[lang] else plan_key
            kb.append([IKB(plan_name, callback_data=f"admin_plan_{plan_key}", style="success")])
        
        kb.append([IKB(LANGS[lang]["cancel"], callback_data="subscription_management", style="danger")])
        
        await update.message.reply_text(
            f"{LANGS[lang]['choose_plan_for_user']}\n\n👤 {username} (ID: {target_user_id})",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        
        return "ADMIN_CHOOSE_PLAN"
        
    elif action == "remove_subscription":
        remove_subscription(target_user_id)
        
        message_text = f"✅ {LANGS[lang]['subscription_removed']}\n\n"
        message_text += f"👤 {username}\n"
        message_text += f"🆔 {target_user_id}\n\n"
        message_text += "تم إزالة الاشتراك بنجاح."
        
        kb = [[IKB(LANGS[lang]["go_back_admin"], callback_data="subscription_management", style="danger")]]
        await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(kb))
    
    ctx.user_data.pop("admin_action", None)
    return ConversationHandler.END

async def handle_admin_choose_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار الباقة"""
    q = update.callback_query
    await q.answer()
    
    admin_id = q.from_user.id
    lang = get_user_lang(admin_id)
    
    if admin_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    plan_key = q.data.replace("admin_plan_", "")
    
    target_user_id = ctx.user_data.get("target_user_id")
    target_username = ctx.user_data.get("target_username")
    
    if not target_user_id:
        await smart_edit(q, "❌ بيانات المستخدم غير موجودة")
        await subscription_management(update, ctx)
        return
    
    success = add_user_subscription(target_user_id, plan_key, admin_id)
    
    if success:
        plan_name = LANGS[lang][f"plan_{plan_key}"] if f"plan_{plan_key}" in LANGS[lang] else plan_key
        
        message_text = f"✅ {LANGS[lang]['subscription_added']}\n\n"
        message_text += f"👤 {target_username}\n"
        message_text += f"🆔 {target_user_id}\n"
        message_text += f"📦 الباقة: {plan_name}\n"
        message_text += f"👑 المانح: {admin_id}\n"
        message_text += f"🕐 الوقت: {time.strftime('%Y-%m-%d %H:%M')}"
        
        # إرسال إشعار للمستخدم
        try:
            sub_info = get_user_subscription_info(target_user_id)
            user_lang = get_user_lang(target_user_id)
            
            user_msg = f"🎉 مبروك! تم تفعيل اشتراكك المميز!\n\n"
            user_msg += f"📦 الباقة: {plan_name}\n"
            user_msg += f"📅 تاريخ الانتهاء: {sub_info['expiry_date']}\n"
            user_msg += f"⏳ الأيام المتبقية: {sub_info['days_left']}\n\n"
            user_msg += "✅ يمكنك الآن استخدام جميع ميزات البوت!"
            
            await ctx.bot.send_message(chat_id=target_user_id, text=user_msg)
        except:
            pass
    else:
        message_text = "❌ فشل إضافة الاشتراك"
    
    kb = [[IKB(LANGS[lang]["go_back_admin"], callback_data="subscription_management", style="danger")]]
    await smart_edit(q, message_text, reply_markup=InlineKeyboardMarkup(kb))
    
    ctx.user_data.pop("target_user_id", None)
    ctx.user_data.pop("target_username", None)
    ctx.user_data.pop("admin_action", None)
    
    return ConversationHandler.END

# ========== Admin Menu ==========
async def admin_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """قائمة الأدمن"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    # زر تفعيل/تعطيل الاشتراك مع لون
    if SUBSCRIPTION_ENABLED:
        toggle_btn = IKB("🟢 تعطيل الاشتراك", callback_data="toggle_sub", style="danger")
    else:
        toggle_btn = IKB("🔴 تفعيل الاشتراك", callback_data="toggle_sub", style="danger")
    
    kb = [
        [toggle_btn],
        [IKB(LANGS[lang]["subscription_management"], callback_data="subscription_management", style="primary")],
        [IKB(LANGS[lang]["stats"], callback_data="admin_stats", style="success")],
        [IKB(LANGS[lang]["broadcast"], callback_data="admin_broadcast", style="primary")],
        [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
    ]
    
    status_text = "🟢 مفعل" if SUBSCRIPTION_ENABLED else "🔴 معطل"
    await smart_edit(q, f"{LANGS[lang]['admin_menu']}\n\n📊 حالة الاشتراك: {status_text}", 
                             reply_markup=InlineKeyboardMarkup(kb))

async def admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إحصائيات البوت"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    stats = get_user_stats()
    
    stats_text = f"📊 إحصائيات البوت:\n\n"
    stats_text += f"👥 إجمالي المستخدمين: {stats['total']}\n"
    stats_text += f"🟢 المستخدمين النشطين: {stats['active']}\n"
    stats_text += f"⭐ المشتركين المميزين: {stats['premium']}\n"
    stats_text += f"\n📈 نسبة النشاط: {(stats['active']/max(stats['total'], 1))*100:.1f}%"
    
    kb = [[IKB(LANGS[lang]["back"], callback_data="admin_menu", style="danger")]]
    await smart_edit(q, stats_text, reply_markup=InlineKeyboardMarkup(kb))

async def admin_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """بدء عملية البث"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    kb = [[IKB(LANGS[lang]["cancel"], callback_data="admin_menu", style="danger")]]
    
    await smart_edit(q, LANGS[lang]["enter_broadcast"], reply_markup=InlineKeyboardMarkup(kb))
    
    ctx.user_data["broadcast_mode"] = True
    
    return BROADCAST_MODE

async def broadcast_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة البث - نسخة مصححة"""
    if not ctx.user_data.get("broadcast_mode"):
        return
    
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        ctx.user_data["broadcast_mode"] = False
        return ConversationHandler.END
    
    message_text = update.message.text
    
    # حفظ نص البث مؤقتاً
    ctx.user_data["broadcast_text"] = message_text
    
    kb = [
        [IKB("✅ نعم، أرسل للجميع", callback_data="confirm_broadcast", style="success")],
        [IKB("❌ لا، إلغاء", callback_data="cancel_broadcast", style="danger")]
    ]
    
    preview_text = f"📢 معاينة رسالة البث:\n\n{message_text}\n\n"
    preview_text += f"📊 سترسل لـ ~{len(get_all_users())} مستخدم\n\n"
    preview_text += "⚠️ هل أنت متأكد من الإرسال؟"
    
    await update.message.reply_text(preview_text, reply_markup=InlineKeyboardMarkup(kb))
    
    ctx.user_data["broadcast_mode"] = "confirming"
    
    return ConversationHandler.END

async def confirm_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تأكيد إرسال البث - نسخة مصححة"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        return
    
    if q.data == "cancel_broadcast":
        await smart_edit(q, "❌ تم إلغاء البث")
        ctx.user_data.pop("broadcast_mode", None)
        ctx.user_data.pop("broadcast_text", None)
        await admin_menu(update, ctx)
        return
    
    message_text = ctx.user_data.get("broadcast_text", "")
    
    if not message_text:
        await smart_edit(q, "❌ لا يوجد نص للبث")
        ctx.user_data.pop("broadcast_mode", None)
        await admin_menu(update, ctx)
        return
    
    users = get_all_users()
    total_users = len(users)
    
    if total_users == 0:
        await smart_edit(q, "❌ لا يوجد مستخدمين لإرسال البث لهم.")
        ctx.user_data.pop("broadcast_mode", None)
        ctx.user_data.pop("broadcast_text", None)
        await admin_menu(update, ctx)
        return
    
    # تحديث الرسالة لإظهار التقدم
    progress_msg = await smart_edit(q, f"🔄 جاري إرسال الرسالة...\n\n📊 0/{total_users} (0%)")
    
    sent_count = 0
    failed_count = 0
    failed_users = []
    
    try:
        # إرسال الرسالة للمستخدمين مع تحديث التقدم
        for index, user in enumerate(users):
            try:
                await ctx.bot.send_message(
                    chat_id=user,
                    text=f"📢 إشعار من الإدارة:\n\n{message_text}\n\n✨ @{BOT_USERNAME.replace('@', '')}"
                )
                sent_count += 1
                
            except Exception as e:
                error_msg = str(e)
                if "chat not found" in error_msg.lower() or "user is deactivated" in error_msg.lower():
                    failed_users.append(f"{user} (حساب محذوف)")
                elif "bot was blocked" in error_msg.lower():
                    failed_users.append(f"{user} (حظر البوت)")
                else:
                    failed_users.append(f"{user} ({error_msg[:50]})")
                failed_count += 1
            
            # تحديث حالة التقدم كل 10 مستخدمين
            if (index + 1) % 10 == 0 or (index + 1) == total_users:
                progress = ((index + 1) / total_users) * 100
                try:
                    await progress_msg.edit_text(
                        f"🔄 جاري إرسال الرسالة...\n\n"
                        f"📊 {index + 1}/{total_users} ({progress:.1f}%)\n"
                        f"✅ تم إرسال: {sent_count}\n"
                        f"❌ فشل: {failed_count}"
                    )
                except:
                    pass
            
            # تأخير بسيط لمنع Flood (أقل من السابق)
            await asyncio.sleep(0.05)
        
        # عرض النتائج النهائية
        result_text = f"✅ تم إرسال البث بنجاح!\n\n"
        result_text += f"📊 الإحصائيات:\n"
        result_text += f"• إجمالي المستخدمين: {total_users}\n"
        result_text += f"• تم الإرسال بنجاح: {sent_count}\n"
        result_text += f"• فشل الإرسال: {failed_count}\n"
        result_text += f"• نسبة النجاح: {(sent_count/max(total_users, 1))*100:.1f}%\n"
        
        if failed_count > 0:
            result_text += f"\n⚠️ تفاصيل الأخطاء:\n"
            if len(failed_users) > 10:
                result_text += f"• أول 10 أخطاء من {failed_count}:\n"
                for i, failed in enumerate(failed_users[:10]):
                    result_text += f"  {i+1}. {failed}\n"
            else:
                for i, failed in enumerate(failed_users):
                    result_text += f"  {i+1}. {failed}\n"
        
        await smart_edit(q, result_text)
        
    except Exception as e:
        error_msg = str(e)
        await smart_edit(q, f"❌ حدث خطأ أثناء البث:\n\n{error_msg}")
        print(f"Broadcast error: {error_msg}")
    
    # تنظيف البيانات
    ctx.user_data.pop("broadcast_mode", None)
    ctx.user_data.pop("broadcast_text", None)
    
    # العودة لقائمة الأدمن بعد 5 ثواني
    await asyncio.sleep(5)
    await admin_menu(update, ctx)

async def return_to_admin_menu(ctx: ContextTypes.DEFAULT_TYPE, user_id: int, lang: str):
    """العودة إلى قائمة الأدمن"""
    try:
        # زر تفعيل/تعطيل الاشتراك مع لون
        if SUBSCRIPTION_ENABLED:
            toggle_btn = IKB("🟢 تعطيل الاشتراك", callback_data="toggle_sub", style="danger")
        else:
            toggle_btn = IKB("🔴 تفعيل الاشتراك", callback_data="toggle_sub", style="danger")
        
        kb = [
            [toggle_btn],
            [IKB(LANGS[lang]["subscription_management"], callback_data="subscription_management", style="primary")],
            [IKB(LANGS[lang]["stats"], callback_data="admin_stats", style="success")],
            [IKB(LANGS[lang]["broadcast"], callback_data="admin_broadcast", style="primary")],
            [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
        ]
        
        status_text = "🟢 مفعل" if SUBSCRIPTION_ENABLED else "🔴 معطل"
        
        await ctx.bot.send_message(
            chat_id=user_id,
            text=f"{LANGS[lang]['admin_menu']}\n\n📊 حالة الاشتراك: {status_text}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except Exception as e:
        print(f"Error returning to admin menu: {e}")

# ========== Subscription Handlers ==========
async def subscribe_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """قائمة الاشتراكات للمستخدمين"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if not SUBSCRIPTION_ENABLED:
        await smart_edit(q, LANGS[lang]["sub_disabled"])
        return
    
    # معلومات اشتراك المستخدم الحالية
    sub_info = get_user_subscription_info(user_id)
    current_status = ""
    
    if sub_info["active"]:
        current_status = f"\n\n⭐ أنت مشترك حالياً:\n"
        current_status += f"📦 {sub_info['plan']}\n"
        current_status += f"📅 تنتهي في: {sub_info['expiry_date']}\n"
        current_status += f"⏳ الأيام المتبقية: {sub_info['days_left']}\n"
    
    message_text = f"{LANGS[lang]['subscribe_title']}{current_status}\n\n"
    message_text += "💳 طرق الدفع:\n"
    message_text += "1. تحويل مباشر للمطور\n"
    message_text += "2. بعد التحويل أرسل إيصال الدفع للمطور\n"
    message_text += "3. سيتم تفعيل اشتراكك فوراً\n\n"
    message_text += f"👤 للمساعدة: @{OWNER_USER}"
    
    kb = []
    for plan_key, plan in SUBSCRIPTION_PLANS.items():
        plan_name = LANGS[lang][f"plan_{plan_key}"] if f"plan_{plan_key}" in LANGS[lang] else plan_key
        price = plan["price"]
        days = plan["days"]
        kb.append([IKB(f"{plan_name} - {price}$", callback_data=f"pay_{plan_key}", style="success")])
    
    kb.append([IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")])
    
    await smart_edit(q, message_text, reply_markup=InlineKeyboardMarkup(kb))

async def handle_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة الدفع"""
    q = update.callback_query
    await q.answer()
    
    plan_key = q.data.replace("pay_", "")
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    
    if not plan:
        return
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    # إرسال معلومات الدفع
    payment_text = f"💳 تفاصيل الدفع للباقة {plan['name']['ar']}:\n\n"
    payment_text += f"💰 السعر: {plan['price']}$\n"
    payment_text += f"⏳ المدة: {plan['days']} يوم\n\n"
    payment_text += "📋 خطوات الدفع:\n"
    payment_text += "1. قم بتحويل المبلغ للمطور\n"
    payment_text += "2. أرسل إيصال التحويل للمطور\n"
    payment_text += "3. انتظر تفعيل الاشتراك\n\n"
    payment_text += f"👤 المطور: @{OWNER_USER}\n\n"
    payment_text += "⚠️ ملاحظة: لن يتم تفعيل الاشتراك إلا بعد وصول الدفع"
    
    kb = [
        [IKB("👤 التواصل مع المطور", url=f"https://t.me/{OWNER_USER}", style="primary")],
        [IKB(LANGS[lang]["back"], callback_data="subscribe", style="danger")]
    ]
    
    await smart_edit(q, payment_text, reply_markup=InlineKeyboardMarkup(kb))

async def toggle_subscription(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تفعيل/تعطيل نظام الاشتراك"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in ADMIN_IDS:
        await smart_edit(q, "⚠️ ليس لديك صلاحية الوصول لهذه القائمة.")
        await main_menu(q, ctx, lang)
        return
    
    global SUBSCRIPTION_ENABLED
    SUBSCRIPTION_ENABLED = not SUBSCRIPTION_ENABLED
    
    status = "مُفعَّل" if SUBSCRIPTION_ENABLED else "معطَّل"
    status_en = "Enabled" if SUBSCRIPTION_ENABLED else "Disabled"
    
    await smart_edit(q, f"✅ نظام الاشتراك أصبح: {status}\n✅ Subscription system: {status_en}")
    await admin_menu(update, ctx)

async def back_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """العودة للقائمة الرئيسية"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if "broadcast_mode" in ctx.user_data:
        ctx.user_data["broadcast_mode"] = False
    
    await main_menu(q, ctx, lang)

# ========== Text Flow ==========
async def send_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """بدء إنشاء استيكر نصي"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await smart_edit(q, 
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return
    
    kb = [[IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]]
    await smart_edit(q, LANGS[lang]["send_text"], reply_markup=InlineKeyboardMarkup(kb))
    
    return TEXT_RECEIVED

async def text_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال النص"""
    user = update.effective_user
    user_id = user.id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await update.message.reply_text(
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return ConversationHandler.END
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    
    USER_DATA[user_id]["text"] = update.message.text
    USER_DATA[user_id]["effects"] = []
    
    # اختيار ترتيب النص (سطر واحد أو سطرين)
    kb = [
        [IKB(LANGS[lang]["style_one_line"], callback_data="arrangement_one_line", style="success")],
        [IKB(LANGS[lang]["style_two_lines"], callback_data="arrangement_two_lines", style="primary")],
        [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
    ]
    
    await update.message.reply_text(LANGS[lang]["text_style_choice"], reply_markup=InlineKeyboardMarkup(kb))
    
    return TEXT_ARRANGEMENT

async def text_arrangement_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """اختيار ترتيب النص"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    
    USER_DATA[user_id]["text_arrangement"] = q.data.replace("arrangement_", "")
    
    # أزرار الخطوط مع إضافة الخطوط العربية والإنجليزية الجديدة
    kb = [
        [IKB(LANGS[lang]["font_arial"], callback_data="font_arial", style="success"),
         IKB(LANGS[lang]["font_bold"], callback_data="font_bold", style="primary")],
        [IKB(LANGS[lang]["font_times"], callback_data="font_times", style="success"),
         IKB(LANGS[lang]["font_courier"], callback_data="font_courier", style="primary")],
        [IKB(LANGS[lang]["font_impact"], callback_data="font_impact", style="success"),
         IKB(LANGS[lang]["font_comic"], callback_data="font_comic", style="primary")],
        [IKB(LANGS[lang]["font_arabic"], callback_data="font_arabic", style="success"),
         IKB(LANGS[lang]["font_arabic_thuluth"], callback_data="font_arabic_thuluth", style="primary")],
        [IKB(LANGS[lang]["font_arabic_naskh"], callback_data="font_arabic_naskh", style="success"),
         IKB(LANGS[lang]["font_arabic_diwani"], callback_data="font_arabic_diwani", style="primary")],
        [IKB(LANGS[lang]["font_arabic_ruqaa"], callback_data="font_arabic_ruqaa", style="success"),
         IKB(LANGS[lang]["font_english_gothic"], callback_data="font_english_gothic", style="primary")],
        [IKB(LANGS[lang]["font_english_cursive"], callback_data="font_english_cursive", style="success"),
         IKB(LANGS[lang]["font_english_modern"], callback_data="font_english_modern", style="primary")],
        [IKB(LANGS[lang]["font_fancy"], callback_data="font_fancy", style="success"),
         IKB(LANGS[lang]["font_script"], callback_data="font_script", style="primary")],
        [IKB(LANGS[lang]["font_3d"], callback_data="font_3d", style="success"),
         IKB(LANGS[lang]["font_rounded"], callback_data="font_rounded", style="primary")],
        [IKB(LANGS[lang]["font_graffiti"], callback_data="font_graffiti", style="success"),
         IKB(LANGS[lang]["font_old"], callback_data="font_old", style="primary")],
        [IKB(LANGS[lang]["font_modern"], callback_data="font_modern", style="success")],
        [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
    ]
    
    await smart_edit(q, LANGS[lang]["choose_font"], reply_markup=InlineKeyboardMarkup(kb))
    
    return FONT_CHOICE

async def font_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """اختيار الخط"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    
    USER_DATA[user_id]["font"] = q.data.replace("font_", "")
    
    # أزرار الأنماط مع تأثيرات الزخارف الجديدة
    kb = [
        [IKB(LANGS[lang]["style_3d"], callback_data="style_3d", style="primary"),
         IKB(LANGS[lang]["style_3d_gold"], callback_data="style_3d_gold", style="success")],
        [IKB(LANGS[lang]["style_3d_building"], callback_data="style_3d_building", style="primary"),
         IKB(LANGS[lang]["style_3d_crystal"], callback_data="style_3d_crystal", style="success")],
        [IKB(LANGS[lang]["style_arabic_calligraphy"], callback_data="style_arabic_calligraphy", style="primary"),
         IKB(LANGS[lang]["style_english_fancy"], callback_data="style_english_fancy", style="success")],
        [IKB(LANGS[lang]["style_arabic_pattern"], callback_data="style_arabic_pattern", style="primary"),
         IKB(LANGS[lang]["style_english_pattern"], callback_data="style_english_pattern", style="success")],
        [IKB(LANGS[lang]["style_cartoon"], callback_data="style_cartoon", style="primary"),
         IKB(LANGS[lang]["style_arabic"], callback_data="style_arabic", style="success")],
        [IKB(LANGS[lang]["style_metal"], callback_data="style_metal", style="primary"),
         IKB(LANGS[lang]["style_neon"], callback_data="style_neon", style="success")],
        [IKB(LANGS[lang]["style_gradient"], callback_data="style_gradient", style="primary")],
        [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
    ]
    
    await smart_edit(q, LANGS[lang]["choose_style"], reply_markup=InlineKeyboardMarkup(kb))
    
    return STYLE_CHOICE

async def style_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """اختيار الأسلوب"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    
    USER_DATA[user_id]["style"] = q.data
    
    # أزرار التأثيرات مع التأثيرات الجديدة
    kb = [
        [IKB(LANGS[lang]["effect_shadow"], callback_data="effect_shadow", style="success"),
         IKB(LANGS[lang]["effect_glow"], callback_data="effect_glow", style="primary")],
        [IKB(LANGS[lang]["effect_reflection"], callback_data="effect_reflection", style="success"),
         IKB(LANGS[lang]["effect_water"], callback_data="effect_water", style="primary")],
        [IKB(LANGS[lang]["effect_arabic_ornament"], callback_data="effect_arabic_ornament", style="success"),
         IKB(LANGS[lang]["effect_english_ornament"], callback_data="effect_english_ornament", style="primary")],
        [IKB(LANGS[lang]["effect_3d_depth"], callback_data="effect_3d_depth", style="success"),
         IKB(LANGS[lang]["effect_glossy"], callback_data="effect_glossy", style="primary")],
        [IKB(LANGS[lang]["effect_frame"], callback_data="effect_frame", style="success"),
         IKB(LANGS[lang]["effect_neon"], callback_data="effect_neon", style="primary")],
        [IKB(LANGS[lang]["effect_gradient"], callback_data="effect_gradient", style="success"),
         IKB(LANGS[lang]["effect_3d_bevel"], callback_data="effect_3d_bevel", style="primary")],
        [IKB(LANGS[lang]["effect_blur"], callback_data="effect_blur", style="success"),
         IKB(LANGS[lang]["effect_sparkle"], callback_data="effect_sparkle", style="primary")],
        [IKB(LANGS[lang]["effect_gold_leaf"], callback_data="effect_gold_leaf", style="success"),
         IKB(LANGS[lang]["effect_crystal_shine"], callback_data="effect_crystal_shine", style="primary")],
        [IKB(LANGS[lang]["effect_royal_frame"], callback_data="effect_royal_frame", style="success"),
         IKB(LANGS[lang]["effect_luxury_border"], callback_data="effect_luxury_border", style="primary")],
        [IKB(LANGS[lang]["finish_effects"], callback_data="finish_effects", style="success")],
        [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
    ]
    
    effects_text = f"✨ {LANGS[lang]['choose_effect']}"
    if USER_DATA[user_id].get("effects"):
        selected_effects = USER_DATA[user_id]["effects"]
        effects_list = [LANGS[lang].get(e, e.replace("effect_", "")) for e in selected_effects if LANGS[lang].get(e)]
        effects_text += f"\n\n✅ التأثيرات المختارة: {', '.join(effects_list)}"
    
    await smart_edit(q, effects_text, reply_markup=InlineKeyboardMarkup(kb))
    
    return EFFECT_CHOICE

async def effect_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """اختيار التأثير"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    
    if "effects" not in USER_DATA[user_id]:
        USER_DATA[user_id]["effects"] = []
    
    effect = q.data
    
    if effect == "finish_effects":
        kb = build_color_palette_kb(lang, prefix="color_")
        
        await smart_edit(q, LANGS[lang]["choose_color"], reply_markup=InlineKeyboardMarkup(kb))
        
        return COLOR_CHOICE
    
    if effect not in USER_DATA[user_id]["effects"]:
        USER_DATA[user_id]["effects"].append(effect)
    else:
        USER_DATA[user_id]["effects"].remove(effect)
    
    # تحديث الأزرار مع التأثيرات الجديدة
    kb = [
        [IKB(LANGS[lang]["effect_shadow"], callback_data="effect_shadow", style="success"),
         IKB(LANGS[lang]["effect_glow"], callback_data="effect_glow", style="primary")],
        [IKB(LANGS[lang]["effect_reflection"], callback_data="effect_reflection", style="success"),
         IKB(LANGS[lang]["effect_water"], callback_data="effect_water", style="primary")],
        [IKB(LANGS[lang]["effect_arabic_ornament"], callback_data="effect_arabic_ornament", style="success"),
         IKB(LANGS[lang]["effect_english_ornament"], callback_data="effect_english_ornament", style="primary")],
        [IKB(LANGS[lang]["effect_3d_depth"], callback_data="effect_3d_depth", style="success"),
         IKB(LANGS[lang]["effect_glossy"], callback_data="effect_glossy", style="primary")],
        [IKB(LANGS[lang]["effect_frame"], callback_data="effect_frame", style="success"),
         IKB(LANGS[lang]["effect_neon"], callback_data="effect_neon", style="primary")],
        [IKB(LANGS[lang]["effect_gradient"], callback_data="effect_gradient", style="success"),
         IKB(LANGS[lang]["effect_3d_bevel"], callback_data="effect_3d_bevel", style="primary")],
        [IKB(LANGS[lang]["effect_blur"], callback_data="effect_blur", style="success"),
         IKB(LANGS[lang]["effect_sparkle"], callback_data="effect_sparkle", style="primary")],
        [IKB(LANGS[lang]["effect_gold_leaf"], callback_data="effect_gold_leaf", style="success"),
         IKB(LANGS[lang]["effect_crystal_shine"], callback_data="effect_crystal_shine", style="primary")],
        [IKB(LANGS[lang]["effect_royal_frame"], callback_data="effect_royal_frame", style="success"),
         IKB(LANGS[lang]["effect_luxury_border"], callback_data="effect_luxury_border", style="primary")],
        [IKB(LANGS[lang]["finish_effects"], callback_data="finish_effects", style="success")],
        [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
    ]
    
    effects_text = f"✨ {LANGS[lang]['choose_effect']}"
    selected_effects = USER_DATA[user_id]["effects"]
    
    if selected_effects:
        effects_list = [LANGS[lang].get(e, e.replace("effect_", "")) for e in selected_effects if LANGS[lang].get(e)]
        effects_text += f"\n\n✅ التأثيرات المختارة: {', '.join(effects_list)}"
    
    await smart_edit(q, effects_text, reply_markup=InlineKeyboardMarkup(kb))
    
    return EFFECT_CHOICE

async def color_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """اختيار اللون"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    
    data = q.data
    
    # الخطوة 1: دوس على "لون مشترك" -> نطلب منه يختار أول لون
    if data == "color_dual":
        kb = build_color_palette_kb(lang, prefix="dual1_", include_dual=False)
        await smart_edit(q, f"1️⃣ {LANGS[lang]['choose_color_dual_first']}", reply_markup=InlineKeyboardMarkup(kb))
        return COLOR_CHOICE
    
    # الخطوة 2: بعد ما اختار أول لون -> نخزنه ونطلب اللون التاني
    if data.startswith("dual1_"):
        USER_DATA[user_id]["_dual_color1"] = data.replace("dual1_", "")
        kb = build_color_palette_kb(lang, prefix="dual2_", include_dual=False)
        await smart_edit(q, f"2️⃣ {LANGS[lang]['choose_color_dual_second']}", reply_markup=InlineKeyboardMarkup(kb))
        return COLOR_CHOICE
    
    # الخطوة 3: بعد اختيار اللون التاني -> نجمع اللونين فى لون مشترك واحد ونكمل عادي
    if data.startswith("dual2_"):
        color1 = USER_DATA[user_id].pop("_dual_color1", "gold")
        color2 = data.replace("dual2_", "")
        USER_DATA[user_id]["color"] = f"dual:{color1}:{color2}"
    else:
        USER_DATA[user_id]["color"] = data.replace("color_", "")
    
    kb_rows = []
    for i in range(0, len(CUSTOM_EMOJIS), 10):
        row = [IKB(e, callback_data=f"emoji_{j}", style="primary") for j, e in enumerate(CUSTOM_EMOJIS[i:i+10])]
        kb_rows.append(row)
    
    kb_rows.append([IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")])
    
    await smart_edit(q, LANGS[lang]["choose_emoji"], reply_markup=InlineKeyboardMarkup(kb_rows))
    
    return EMOJI_CHOICE

async def emoji_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """اختيار الإيموجى"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    
    idx = int(q.data.split("_")[1])
    USER_DATA[user_id]["emoji"] = CUSTOM_EMOJIS[idx]
    
    # اتشال زر "إيموجي عادي" من هنا (فيه خيار الاستيكر العادي أصلاً من القائمة
    # الرئيسية "🎭 استيكر عادى")، فبقينا نكمل مباشرة كإيموجي مميز من غير
    # قائمة اختيار إضافية
    USER_DATA[user_id]["sticker_type"] = "custom_emoji"
    
    await smart_edit(q, LANGS[lang]["generating"])
    await generate_verified_emoji_sticker(q, ctx)
    
    return ConversationHandler.END

async def sticker_type_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """اختيار نوع الاستيكر: إيموجي مميز أو إيموجي/استيكر عادي"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    
    USER_DATA[user_id]["sticker_type"] = q.data.replace("stickertype_", "")
    
    await smart_edit(q, LANGS[lang]["generating"])
    await generate_verified_emoji_sticker(q, ctx)
    
    return ConversationHandler.END

# ========== Core Generator - FIXED VERSION ==========
async def generate_verified_emoji_sticker(q, ctx):
    """إنشاء الاستيكر - نسخة مصححة"""
    user_id = q.from_user.id
    chat_id = q.message.chat_id
    lang = get_user_lang(user_id)
    
    if user_id not in USER_DATA:
        await smart_edit(q, f"{LANGS[lang]['error']} بيانات المستخدم غير موجودة")
        await main_menu(q, ctx, lang)
        return
    
    data = USER_DATA[user_id]
    text = data.get("text", "")
    style = data.get("style", "style_3d")
    color = data.get("color", "gold")
    emoji = data.get("emoji", CUSTOM_EMOJIS[0])
    font_type = data.get("font", "arial")
    effects = data.get("effects", [])
    text_arrangement = data.get("text_arrangement", "one_line")
    
    if not text:
        await smart_edit(q, f"{LANGS[lang]['error']} النص غير موجود")
        await main_menu(q, ctx, lang)
        return
    
    try:
        # إنشاء صورة واحدة للنص كامل
        img = create_sticker_image(text, style, color, font_type, effects, emoji, text_arrangement)
        
        path = f"{tempfile.gettempdir()}/sticker_{int(time.time())}_{user_id}.png"
        img.save(path, "PNG")
        
        # التحقق من أبعاد الصورة وإصلاحها
        validated_path = validate_image_dimensions(path)
        if validated_path != path:
            os.remove(path)
            path = validated_path
        
        # ضغط الصورة للرموز المميزة (حد 256KB)
        file_size = os.path.getsize(path) / 1024
        print(f"Initial image size: {file_size:.1f}KB")
        
        if file_size > 256:
            print(f"Image size {file_size:.1f}KB is too large for custom emoji, compressing...")
            compressed_path = compress_image(path, 256)
            if compressed_path != path and os.path.exists(compressed_path):
                os.remove(path)
                path = compressed_path
                file_size = os.path.getsize(path) / 1024
                print(f"After compression: {file_size:.1f}KB")
        
        # إنشاء اسمين مختلفين للرموز المميزة والاستيكرات العادية
        timestamp = int(time.time())
        unique_hash = hashlib.md5(f"{user_id}{timestamp}".encode()).hexdigest()[:8]
        bot_name = BOT_USERNAME.replace("@", "").replace(".", "_").lower()
        
        # إنشاء اسمين مختلفين
        emoji_set_name = f"emoji{unique_hash}_by_{bot_name}"
        sticker_set_name = f"sticker{unique_hash}_by_{bot_name}"
        
        # تنظيف الأسماء
        emoji_set_name = sanitize_sticker_set_name(emoji_set_name)
        sticker_set_name = sanitize_sticker_set_name(sticker_set_name)
        
        # استخدام اسم الرموز المميزة (أو اسم الاستيكر العادي لو المستخدم اختار "إيموجي عادي")
        wanted_sticker_type = data.get("sticker_type", "custom_emoji")
        set_name = sticker_set_name if wanted_sticker_type == "regular" else emoji_set_name
        
        with open(path, "rb") as f:
            sticker_data = f.read()
            
            # فحص الحجم في الذاكرة
            data_size_kb = len(sticker_data) / 1024
            print(f"Sticker data size in memory: {data_size_kb:.1f}KB")
            
            if data_size_kb > 256:
                # محاولة ضغط إضافي
                await smart_edit(q, f"❌ حجم الاستيكر كبير جداً ({data_size_kb:.1f}KB). جاري الضغط...")
                
                # حفظ الصورة المؤقتة
                temp_path = f"{tempfile.gettempdir()}/temp_compress_{user_id}.png"
                with Image.open(path) as temp_img:
                    # تقليل الجودة أكثر
                    if temp_img.mode != 'RGBA':
                        temp_img = temp_img.convert('RGBA')
                    temp_img.save(temp_path, "PNG", optimize=True, quality=30)
                
                with open(temp_path, "rb") as tf:
                    sticker_data = tf.read()
                    data_size_kb = len(sticker_data) / 1024
                    print(f"After aggressive compression: {data_size_kb:.1f}KB")
                    
                    if data_size_kb > 256:
                        await smart_edit(q, f"❌ حجم الاستيكر كبير جداً حتى بعد الضغط ({data_size_kb:.1f}KB). الحد الأقصى للرموز المميزة هو 256KB.")
                        try:
                            os.remove(path)
                            os.remove(temp_path)
                        except:
                            pass
                        await main_menu(q, ctx, lang)
                        return
                
                path = temp_path
            
            sticker = InputSticker(
                sticker=sticker_data,
                emoji_list=[emoji],
                format="static"
            )
            
            # إرسال إشارة "جاري التحميل"
            try:
                await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
            except:
                pass
            
            title = f"✨ {text[:20]}" if len(text) > 20 else f"✨ {text}"
            
            # لو المستخدم اختار "😊 إيموجي عادي" (مش مميز)، ننشئه كاستيكر عادي مباشرة
            # من غير ما نمر بمحاولات الرمز المميز (100x100 / 256KB) خالص
            if wanted_sticker_type == "regular":
                await asyncio.sleep(1)
                await fallback_to_regular_sticker(ctx, user_id, set_name, title, sticker, lang, chat_id)
                return
            
            # إضافة تأخير لمنع Flood control
            await asyncio.sleep(1)
            
            # محاولة إنشاء كإيموجي مميز
            try:
                result = await ctx.bot.create_new_sticker_set(
                    user_id=user_id,
                    name=set_name,
                    title=title,
                    stickers=[sticker],
                    sticker_type="custom_emoji"
                )
                
                # حفظ الرابط في قاعدة البيانات
                save_sticker_link(user_id, set_name, title, is_custom_emoji=True)
                
                # إرسال رسالة نجاح فورية
                success_msg = f"✅ تم إنشاء رمزية مميزة بنجاح!\n\n"
                success_msg += f"🔗 رابط الحزمة:\nhttps://t.me/addstickers/{set_name}\n\n"
                success_msg += f"📊 الحجم: {data_size_kb:.1f}KB"
                
                # إنشاء كيبورد مع زر الرابط
                kb = [
                    [IKB("✨ إضافة الرمزية المميزة", url=f"https://t.me/addstickers/{set_name}", style="success")],
                    [copy_link_ikb(set_name, style="primary")],
                    [IKB("📂 رموزي المميزة", callback_data="my_stickers", style="success")],
                    [IKB("🔙 القائمة الرئيسية", callback_data="back_main", style="danger")]
                ]
                
                try:
                    await q.delete_message()
                except:
                    pass
                
                # إرسال الرسالة
                msg = await ctx.bot.send_message(
                    chat_id=chat_id,
                    text=success_msg,
                    reply_markup=InlineKeyboardMarkup(kb),
                    disable_web_page_preview=False
                )
                
                # إضافة تأخير لمنع Flood control
                await asyncio.sleep(2)
                
            except Exception as custom_error:
                error_msg = str(custom_error)
                print(f"Custom emoji error: {error_msg}")
                
                # تحليل الخطأ
                if "Flood control exceeded" in error_msg:
                    # استخراج وقت الانتظار من رسالة الخطأ
                    try:
                        wait_time = int(error_msg.split("Retry in ")[1].split(" ")[0])
                        await smart_edit(q, f"⏳ يرجى الانتظار {wait_time} ثانية بسبب كثرة الطلبات...")
                        await asyncio.sleep(wait_time + 5)
                        
                        # إعادة المحاولة بعد الانتظار
                        try:
                            result = await ctx.bot.create_new_sticker_set(
                                user_id=user_id,
                                name=set_name,
                                title=title,
                                stickers=[sticker],
                                sticker_type="custom_emoji"
                            )
                            
                            save_sticker_link(user_id, set_name, title, is_custom_emoji=True)
                            
                            success_msg = f"✅ تم إنشاء رمزية مميزة بنجاح بعد الانتظار!\n\n"
                            success_msg += f"🔗 رابط الحزمة:\nhttps://t.me/addstickers/{set_name}"
                            
                            kb = [
                                [IKB("✨ إضافة الرمزية المميزة", url=f"https://t.me/addstickers/{set_name}", style="primary")],
                                [copy_link_ikb(set_name, style="success")],
                                [IKB("🔙 القائمة الرئيسية", callback_data="back_main", style="danger")]
                            ]
                            
                            await ctx.bot.send_message(
                                chat_id=chat_id,
                                text=success_msg,
                                reply_markup=InlineKeyboardMarkup(kb)
                            )
                            
                        except Exception as retry_error:
                            print(f"Retry also failed: {retry_error}")
                            await fallback_to_regular_sticker(ctx, user_id, sticker_set_name, title, sticker, lang, chat_id)
                            
                    except:
                        await fallback_to_regular_sticker(ctx, user_id, sticker_set_name, title, sticker, lang, chat_id)
                        
                elif "Sticker_png_dimensions" in error_msg:
                    # الخطأ بسبب أبعاد PNG
                    try:
                        await smart_edit(q, "⚠️ مشكلة في أبعاد الصورة، جاري الإصلاح...")
                        
                        with Image.open(path) as image:
                            # تأكد من الأبعاد الصحيحة
                            if image.mode != 'RGBA':
                                image = image.convert('RGBA')
                            
                            if image.size != (100, 100):
                                image = image.resize((100, 100), Image.LANCZOS)
                            
                            corrected_path = f"{tempfile.gettempdir()}/corrected_{int(time.time())}_{user_id}.png"
                            image.save(corrected_path, "PNG", optimize=True)
                            
                            with open(corrected_path, "rb") as corrected_f:
                                corrected_data = corrected_f.read()
                                corrected_sticker = InputSticker(
                                    sticker=corrected_data,
                                    emoji_list=[emoji],
                                    format="static"
                                )
                                
                                try:
                                    await ctx.bot.create_new_sticker_set(
                                        user_id=user_id,
                                        name=set_name,
                                        title=title,
                                        stickers=[corrected_sticker],
                                        sticker_type="custom_emoji"
                                    )
                                    
                                    save_sticker_link(user_id, set_name, title, is_custom_emoji=True)
                                    
                                    success_msg = f"✅ تم إنشاء رمزية مميزة بنجاح!\n\n"
                                    success_msg += f"🔗 رابط الحزمة:\nhttps://t.me/addstickers/{set_name}\n\n"
                                    success_msg += f"📊 الحجم: {len(corrected_data)/1024:.1f}KB"
                                    
                                    kb = [
                                        [IKB("✨ إضافة الرمزية المميزة", url=f"https://t.me/addstickers/{set_name}", style="primary")],
                                        [copy_link_ikb(set_name, style="success")],
                                        [IKB("🔙 القائمة الرئيسية", callback_data="back_main", style="danger")]
                                    ]
                                    
                                    await ctx.bot.send_message(
                                        chat_id=chat_id,
                                        text=success_msg,
                                        reply_markup=InlineKeyboardMarkup(kb)
                                    )
                                    
                                    try:
                                        os.remove(corrected_path)
                                    except:
                                        pass
                                    
                                except Exception as retry_error:
                                    print(f"Retry also failed: {retry_error}")
                                    await fallback_to_regular_sticker(ctx, user_id, sticker_set_name, title, corrected_sticker, lang, chat_id)
                    except Exception as dim_error:
                        print(f"Dimension fixing error: {dim_error}")
                        await fallback_to_regular_sticker(ctx, user_id, sticker_set_name, title, sticker, lang, chat_id)
                
                elif "File is too big" in error_msg:
                    try:
                        await smart_edit(q, f"❌ حجم الملف كبير جداً ({data_size_kb:.1f}KB). جاري المحاولة كاستيكر عادي...")
                    except:
                        pass
                    await fallback_to_regular_sticker(ctx, user_id, sticker_set_name, title, sticker, lang, chat_id)
                
                else:
                    try:
                        await smart_edit(q, f"⚠️ خطأ في إنشاء الرمزية المميزة. جاري المحاولة كاستيكر عادي...")
                    except:
                        pass
                    await fallback_to_regular_sticker(ctx, user_id, sticker_set_name, title, sticker, lang, chat_id)
            
            # تنظيف الملفات
            try:
                os.remove(path)
            except:
                pass
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error creating sticker set: {error_msg}")
        
        # إرسال رسالة خطأ بسيطة
        try:
            await ctx.bot.send_message(
                chat_id=chat_id,
                text=f"❌ حدث خطأ في الإنشاء: {error_msg[:100]}\n\n🔙 العودة للقائمة الرئيسية..."
            )
        except:
            pass
        
        try:
            if 'path' in locals() and os.path.exists(path):
                os.remove(path)
        except:
            pass
        
        await asyncio.sleep(2)
        await main_menu(q, ctx, lang)

async def fallback_to_regular_sticker(ctx, user_id, set_name, title, sticker, lang, chat_id):
    """الرجوع إلى استيكر عادي عند فشل الرمز المميز"""
    try:
        await ctx.bot.create_new_sticker_set(
            user_id=user_id,
            name=set_name,
            title=title,
            stickers=[sticker],
            sticker_type="regular"
        )
        
        save_sticker_link(user_id, set_name, title, is_custom_emoji=False)
        
        success_msg = f"✅ تم إنشاء الاستيكر العادي بنجاح!\n\n"
        success_msg += f"🔗 رابط الحزمة:\nhttps://t.me/addstickers/{set_name}\n\n"
        success_msg += f"📌 ملاحظة: تم إنشاء استيكر عادي بسبب قيود الرموز المميزة"
        
        kb = [
            [IKB(LANGS[lang]["open_link"], url=f"https://t.me/addstickers/{set_name}", style="primary")],
            [copy_link_ikb(set_name, text=LANGS[lang]["copy_link"], style="success")],
            [IKB(LANGS[lang]["my_stickers"], callback_data="my_stickers", style="primary")],
            [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
        ]
        
        await ctx.bot.send_message(
            chat_id=chat_id,
            text=success_msg,
            reply_markup=InlineKeyboardMarkup(kb)
        )
        
    except Exception as fallback_error:
        print(f"Fallback also failed: {fallback_error}")
        
        error_text = f"{LANGS[lang]['error']} فشل في إنشاء الاستيكر.\n\n"
        error_text += "📌 الأسباب المحتملة:\n"
        error_text += "• وصلت للحد الأقصى من حزم الاستيكرات\n"
        error_text += "• اسم الحزمة غير مقبول\n"
        error_text += "• مشكلة في تليجرام API\n\n"
        error_text += f"📞 للمساعدة: @{OWNER_USER}"
        
        await ctx.bot.send_message(
            chat_id=chat_id,
            text=error_text
        )

# ========== Photo Handler ==========
async def photo_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال صورة"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await smart_edit(q, 
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    USER_DATA[user_id]["awaiting"] = "photo"
    
    # سؤال المستخدم عن إزالة الخلفية
    kb = [
        [IKB(LANGS[lang]["remove_bg_yes"], callback_data="remove_bg_yes", style="success")],
        [IKB(LANGS[lang]["remove_bg_no"], callback_data="remove_bg_no", style="primary")],
        [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
    ]
    
    await smart_edit(q, LANGS[lang]["remove_bg_choice"], reply_markup=InlineKeyboardMarkup(kb))
    
    return REMOVE_BG_CHOICE

async def remove_bg_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """اختيار إزالة الخلفية"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    
    USER_DATA[user_id]["remove_bg"] = q.data == "remove_bg_yes"
    
    kb = [[IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]]
    await smart_edit(q, LANGS[lang]["photo"], reply_markup=InlineKeyboardMarkup(kb))
    
    return TEXT_RECEIVED

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة الصورة"""
    user = update.effective_user
    user_id = user.id
    chat_id = update.message.chat_id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await update.message.reply_text(
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return
    
    if USER_DATA.get(user_id, {}).get("awaiting") != "photo":
        return
    
    photo = update.message.photo[-1] if update.message.photo else None
    
    if not photo:
        await update.message.reply_text(f"{LANGS[lang]['error']} لم يتم العثور على صورة")
        return
    
    try:
        await update.message.reply_text(LANGS[lang]["processing_photo"])
        
        file = await ctx.bot.get_file(photo.file_id)
        temp_path = f"{tempfile.gettempdir()}/photo_{user_id}_{int(time.time())}.jpg"
        await file.download_to_drive(temp_path)
        
        img = Image.open(temp_path)
        img.thumbnail((100, 100), Image.LANCZOS)
        
        new_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        x = (100 - img.width) // 2
        y = (100 - img.height) // 2
        new_img.paste(img, (x, y))
        
        # إزالة الخلفية إذا اختار المستخدم ذلك
        remove_bg = USER_DATA.get(user_id, {}).get("remove_bg", False)
        if remove_bg:
            try:
                new_img = remove(new_img)
            except Exception as bg_error:
                print(f"Error removing background: {bg_error}")
                await update.message.reply_text("⚠️ حدث خطأ في إزالة الخلفية، سيتم استخدام الصورة كما هي.")
        
        output_path = f"{tempfile.gettempdir()}/sticker_{user_id}_{int(time.time())}.png"
        new_img.save(output_path, "PNG")
        
        # ضغط الصورة للرموز المميزة
        file_size = os.path.getsize(output_path) / 1024
        if file_size > 256:
            print(f"Photo size {file_size:.1f}KB is too large for custom emoji, compressing...")
            compressed_path = compress_image(output_path, 256)
            output_path = compressed_path
        
        await add_verified_sticker(update, ctx, output_path, lang)
        
        try:
            os.remove(temp_path)
            os.remove(output_path)
        except:
            pass
        
        if user_id in USER_DATA:
            USER_DATA[user_id].pop("awaiting", None)
            USER_DATA[user_id].pop("remove_bg", None)
        
    except Exception as e:
        await update.message.reply_text(f"{LANGS[lang]['error']} {str(e)}")
        print(f"Photo processing error: {e}")

# ========== Video Handler ==========
async def video_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال فيديو"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await smart_edit(q, 
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    USER_DATA[user_id]["awaiting"] = "video"
    
    kb = [[IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]]
    await smart_edit(q, LANGS[lang]["video"], reply_markup=InlineKeyboardMarkup(kb))

async def handle_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة الفيديو - نسخة محسنة"""
    user = update.effective_user
    if not user:
        await update.message.reply_text("❌ لم يتم العثور على بيانات المستخدم")
        return
    
    user_id = user.id
    chat_id = update.message.chat_id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await update.message.reply_text(
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return
    
    if USER_DATA.get(user_id, {}).get("awaiting") != "video":
        return
    
    video = update.message.video
    
    if not video:
        await update.message.reply_text(f"{LANGS[lang]['error']} لم يتم العثور على فيديو")
        return
    
    # فحص الحجم
    if video.file_size and video.file_size > 50 * 1024 * 1024:  # 50MB
        await update.message.reply_text("❌ حجم الفيديو كبير جداً! الحد الأقصى 50MB.")
        return
    
    try:
        await update.message.reply_text(LANGS[lang]["processing_video_with_text"])
        
        file = await ctx.bot.get_file(video.file_id)
        temp_path = f"{tempfile.gettempdir()}/video_{user_id}_{int(time.time())}.mp4"
        await file.download_to_drive(temp_path)
        
        # معالجة الفيديو باستخدام FFmpeg
        processed_path = process_video_to_webm_advanced(temp_path, max_duration=3)
        
        if processed_path != temp_path:
            try:
                os.remove(temp_path)
            except:
                pass
        
        await add_verified_sticker(update, ctx, processed_path, lang, is_video=True)
        
        try:
            if os.path.exists(processed_path):
                os.remove(processed_path)
        except:
            pass
        
        if user_id in USER_DATA:
            USER_DATA[user_id].pop("awaiting", None)
        
    except Exception as e:
        error_msg = str(e)
        print(f"Video processing error: {error_msg}")
        
        await update.message.reply_text(f"{LANGS[lang]['error']} حدث خطأ في معالجة الفيديو. يرجى المحاولة مرة أخرى.")

# ========== Advanced Animated Sticker Handler ==========
async def animated_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال استيكر متحرك"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await smart_edit(q, 
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    USER_DATA[user_id]["awaiting"] = "animated"
    
    text = f"{LANGS[lang]['animated_desc']}\n\n{LANGS[lang]['max_anim_length']}"
    kb = [[IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]]
    
    await smart_edit(q, text, reply_markup=InlineKeyboardMarkup(kb))

async def handle_animated(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة الاستيكر المتحرك - نسخة محسنة"""
    user = update.effective_user
    user_id = user.id
    chat_id = update.message.chat_id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await update.message.reply_text(
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return
    
    if USER_DATA.get(user_id, {}).get("awaiting") != "animated":
        return
    
    document = update.message.document
    animation = update.message.animation
    video = update.message.video
    
    file_to_process = None
    file_type = None
    
    if document and document.mime_type in ["image/gif", "video/mp4", "video/webm"]:
        file_to_process = document
        file_type = "gif" if document.mime_type == "image/gif" else "video"
    elif animation:
        file_to_process = animation
        file_type = "gif"
    elif video:
        file_to_process = video
        file_type = "video"
    else:
        await update.message.reply_text(f"{LANGS[lang]['error']} {LANGS[lang]['invalid_gif']}")
        return
    
    try:
        await update.message.reply_text(LANGS[lang]["processing_anim"])
        
        file = await ctx.bot.get_file(file_to_process.file_id)
        
        unique_id = uuid.uuid4().hex
        temp_path = f"{tempfile.gettempdir()}/anim_{user_id}_{unique_id}"
        
        if file_type == "gif":
            temp_path += ".gif"
            await file.download_to_drive(temp_path)
            
            # تحويل GIF إلى WebM
            processed_path = process_gif_to_webm_advanced(temp_path)
            
            if processed_path != temp_path:
                os.remove(temp_path)
            
            await add_verified_sticker(update, ctx, processed_path, lang, is_video=True)
            
            try:
                if os.path.exists(processed_path):
                    os.remove(processed_path)
            except:
                pass
                
        else:
            temp_path += ".mp4"
            await file.download_to_drive(temp_path)
            
            # معالجة الفيديو
            processed_path = process_video_to_webm_advanced(temp_path, max_duration=3)
            
            if processed_path != temp_path:
                os.remove(temp_path)
            
            await add_verified_sticker(update, ctx, processed_path, lang, is_video=True)
            
            try:
                if os.path.exists(processed_path):
                    os.remove(processed_path)
            except:
                pass
        
        if user_id in USER_DATA:
            USER_DATA[user_id].pop("awaiting", None)
        
    except Exception as e:
        await update.message.reply_text(f"{LANGS[lang]['error']} حدث خطأ في معالجة الملف المتحرك.")
        print(f"Animated sticker error: {e}")

# ========== Regular (Non-Premium) Sticker Handler ==========
async def regular_sticker_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال طلب استيكر عادى (غير مميز) - يقبل صورة/فيديو/GIF"""
    q = update.callback_query
    await q.answer()

    user_id = q.from_user.id
    lang = get_user_lang(user_id)

    is_user_premium = is_premium(user_id)
    if not is_user_premium:
        if not check_and_update_usage(user_id, 3):
            usage_left = 3 - get_today_usage(user_id)
            await smart_edit(q, 
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return

    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    USER_DATA[user_id]["awaiting"] = "regular_sticker"

    kb = [[IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]]
    await smart_edit(q, LANGS[lang]["regular_sticker_desc"], reply_markup=InlineKeyboardMarkup(kb))


async def handle_regular_sticker_media(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة أى صورة/فيديو/GIF وتحويله لاستيكر تلجرام عادى (غير مميز)"""
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    chat_id = update.message.chat_id
    lang = get_user_lang(user_id)

    if USER_DATA.get(user_id, {}).get("awaiting") != "regular_sticker":
        return

    is_user_premium = is_premium(user_id)
    if not is_user_premium:
        if not check_and_update_usage(user_id, 3):
            usage_left = 3 - get_today_usage(user_id)
            await update.message.reply_text(
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return

    photo = update.message.photo[-1] if update.message.photo else None
    animation = update.message.animation
    video = update.message.video
    document = update.message.document

    file_obj = None
    kind = None  # "static" | "video"

    if photo:
        file_obj = photo
        kind = "static"
    elif animation:
        file_obj = animation
        kind = "video"
    elif video:
        file_obj = video
        kind = "video"
    elif document and document.mime_type:
        if document.mime_type.startswith("image/gif"):
            file_obj = document
            kind = "video"
        elif document.mime_type.startswith("image/"):
            file_obj = document
            kind = "static"
        elif document.mime_type.startswith("video/"):
            file_obj = document
            kind = "video"

    if not file_obj:
        await update.message.reply_text(LANGS[lang]["regular_sticker_invalid"])
        return

    try:
        await update.message.reply_text(LANGS[lang]["regular_sticker_processing"])

        tg_file = await ctx.bot.get_file(file_obj.file_id)
        unique_id = uuid.uuid4().hex
        temp_dir = tempfile.gettempdir()
        output_path = None

        if kind == "static":
            temp_path = f"{temp_dir}/regsticker_{user_id}_{unique_id}.jpg"
            await tg_file.download_to_drive(temp_path)

            img = Image.open(temp_path).convert("RGBA")
            # ملصقات تلجرام العادية تحتاج مقاس 512x512 (أحد الأبعاد بالضبط 512)
            img.thumbnail((512, 512), Image.LANCZOS)
            new_img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            paste_x = (512 - img.width) // 2
            paste_y = (512 - img.height) // 2
            new_img.paste(img, (paste_x, paste_y), img)

            output_path = f"{temp_dir}/regsticker_out_{user_id}_{unique_id}.png"
            new_img.save(output_path, "PNG")

            # حد الحجم للاستيكر الثابت العادى هو 512KB
            if os.path.getsize(output_path) / 1024 > 512:
                output_path = compress_image(output_path, 512)

            try:
                os.remove(temp_path)
            except:
                pass

            await add_regular_sticker(update, ctx, output_path, lang, is_video=False)

        else:
            ext = ".gif" if (getattr(file_obj, "mime_type", "") == "image/gif" or animation) else ".mp4"
            temp_path = f"{temp_dir}/regsticker_{user_id}_{unique_id}{ext}"
            await tg_file.download_to_drive(temp_path)

            if ext == ".gif":
                # الاستيكر العادي (regular) لازم يكون 512x512 مش 100x100 زي الرموز المميزة
                processed_path = process_gif_to_webm_advanced(temp_path, target_size=512, max_size_kb=256)
            else:
                processed_path = process_video_to_webm_advanced(temp_path, max_duration=3, max_size_kb=256, target_size=512)

            if processed_path != temp_path:
                try:
                    os.remove(temp_path)
                except:
                    pass

            await add_regular_sticker(update, ctx, processed_path, lang, is_video=True)

        if user_id in USER_DATA:
            USER_DATA[user_id].pop("awaiting", None)

    except Exception as e:
        print(f"Regular sticker processing error: {e}")
        await update.message.reply_text(f"{LANGS[lang]['error']} {str(e)}")


async def add_regular_sticker(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                               path: str, lang: str, is_video: bool = False):
    """إنشاء استيكر تلجرام عادى (sticker_type='regular') مباشرة، بدون المرور بمنطق الرموز المميزة"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            user_id = update.callback_query.from_user.id
            chat_id = update.callback_query.message.chat_id
        elif hasattr(update, 'message') and update.message:
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
        else:
            raise AttributeError("لا يمكن العثور على user_id")
    except:
        user_id = None
        chat_id = None

    if not user_id or not chat_id:
        return

    try:
        timestamp = int(time.time())
        unique_hash = hashlib.md5(f"{user_id}{timestamp}reg".encode()).hexdigest()[:8]
        bot_name = BOT_USERNAME.replace("@", "").replace(".", "_").lower()
        set_name = sanitize_sticker_set_name(f"regular{unique_hash}_by_{bot_name}")
        title = f"🎭 {timestamp}"

        try:
            await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        except:
            pass

        with open(path, "rb") as f:
            sticker_data = f.read()

        data_size_kb = len(sticker_data) / 1024
        max_size = 256 if is_video else 512
        if data_size_kb > max_size:
            await update.message.reply_text(
                f"❌ {LANGS[lang]['file_too_big_after_compression']} ({data_size_kb:.1f}KB)"
            )
            return

        sticker_format = "video" if is_video else "static"
        sticker = InputSticker(
            sticker=sticker_data,
            emoji_list=[CUSTOM_EMOJIS[0]],
            format=sticker_format
        )

        try:
            await ctx.bot.create_new_sticker_set(
                user_id=user_id,
                name=set_name,
                title=title,
                stickers=[sticker],
                sticker_type="regular"
            )
            save_sticker_link(user_id, set_name, title, is_custom_emoji=False, is_video=is_video)
        except Exception as create_error:
            print(f"Regular sticker set error: {create_error}")
            await update.message.reply_text(
                f"{LANGS[lang]['error']} فشل في إنشاء الاستيكر. يرجى المحاولة مرة أخرى."
            )
            return

        sticker_type_text = "استيكر متحرك عادى" if is_video else "استيكر ثابت عادى"
        success_msg = f"✅ تم إنشاء {sticker_type_text} بنجاح!\n\n"
        success_msg += f"🔗 رابط الحزمة:\nhttps://t.me/addstickers/{set_name}\n\n"
        success_msg += f"📌 للحفظ: اضغط على الرابط ثم انسخه"

        kb = [
            [IKB(LANGS[lang]["open_link"], url=f"https://t.me/addstickers/{set_name}", style="success")],
            [copy_link_ikb(set_name, style="primary")],
            [IKB(LANGS[lang]["my_stickers"], callback_data="my_stickers", style="success")],
            [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
        ]

        try:
            await ctx.bot.send_message(chat_id=chat_id, text=success_msg, reply_markup=InlineKeyboardMarkup(kb))
        except Exception as msg_error:
            print(f"Error sending message: {msg_error}")

        try:
            os.remove(path)
        except:
            pass

        if user_id in USER_DATA:
            USER_DATA[user_id].pop("awaiting", None)

    except Exception as e:
        error_msg = str(e)
        print(f"Error creating regular sticker set: {error_msg}")
        if "too many" in error_msg.lower():
            error_msg = "لقد وصلت للحد الأقصى من حزم الاستيكرات."
        elif "File is too big" in error_msg:
            error_msg = "حجم الملف كبير جداً! حاول بملف أصغر."
        try:
            if update.message:
                await update.message.reply_text(f"{LANGS[lang]['error']} {error_msg}")
        except:
            pass


# ========== Enhanced Sticker to Emoji Handler ==========
async def sticker_to_emoji_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تحويل استيكر إلى إيموجي"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await smart_edit(q, 
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return
    
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {}
    USER_DATA[user_id]["awaiting"] = "sticker_to_emoji"
    
    text = "🎭 تحويل الاستيكر إلى رمزية مميزة\n\n"
    text += "أرسل لي أي استيكر (عادي أو متحرك) وسأحوله إلى رمزية مميزة لك!\n\n"
    text += "📊 الحدود:\n"
    text += "• الرموز المميزة المتحركة: 256 كيلوبايت\n"
    text += "• الرموز المميزة الثابتة: 256 كيلوبايت\n\n"
    text += "⚠️ ملاحظة: إذا كان الاستيكر كبيراً، سأحاول ضغطه تلقائياً."
    
    if lang == "en":
        text = "🎭 Convert Sticker to Custom Emoji\n\n"
        text += "Send me any sticker (static or animated) and I'll convert it to custom emoji for you!\n\n"
        text += "📊 Limits:\n"
        text += "• Animated custom emojis: 256KB\n"
        text += "• Static custom emojis: 256KB\n\n"
        text += "⚠️ Note: If the sticker is too big, I'll try to compress it automatically."
    
    kb = [[IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]]
    
    await smart_edit(q, text, reply_markup=InlineKeyboardMarkup(kb))

async def handle_sticker_enhanced(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة الاستيكر وتحويله إلى رمزية مميزة - نسخة محسنة"""
    user = update.effective_user
    user_id = user.id
    chat_id = update.message.chat_id
    lang = get_user_lang(user_id)
    
    # التحقق من الاشتراك أو الاستخدام اليومي
    is_user_premium = is_premium(user_id)
    
    if not is_user_premium:  # إذا لم يكن مشتركاً
        if not check_and_update_usage(user_id, 3):  # حد 3 مرات يومياً
            usage_left = 3 - get_today_usage(user_id)
            await update.message.reply_text(
                f"⚠️ لقد استخدمت الحد اليومي (3 مرات)!\n\n"
                f"📊 باقي لك اليوم: {usage_left} مرات\n\n"
                f"💡 للاستخدام بدون حدود:\n"
                f"1. اشترك في الباقة المدفوعة\n"
                f"2. استخدم جميع الميزات\n"
                f"3. بدون قيود يومية\n\n"
                f"💳 للاشتراك: @{OWNER_USER}"
            )
            return
    
    if USER_DATA.get(user_id, {}).get("awaiting") != "sticker_to_emoji":
        return
    
    sticker = update.message.sticker
    
    if not sticker:
        await update.message.reply_text(f"{LANGS[lang]['error']} لم يتم العثور على استيكر")
        return
    
    try:
        await update.message.reply_text(LANGS[lang]["sticker_processing"])
        
        file = await ctx.bot.get_file(sticker.file_id)
        
        # الاستيكرات المتحركة بصيغة TGS (Lottie) هي ملف JSON مضغوط بـ gzip،
        # مش صورة ولا فيديو — تليجرام بيقبلها زي ما هي (بدون أي تحويل عبر PIL)
        # طالما format="animated". لو حاولنا نفتحها بـ PIL هتدي
        # "cannot identify image file" لأنها مش صورة أصلاً.
        if sticker.is_animated:
            file_extension = "tgs"
        elif sticker.is_video:
            file_extension = "webm"
        else:
            file_extension = "png"
        original_path = f"{tempfile.gettempdir()}/original_{user_id}_{uuid.uuid4().hex}.{file_extension}"
        await file.download_to_drive(original_path)
        
        timestamp = int(time.time())
        unique_hash = hashlib.md5(f"{user_id}{timestamp}".encode()).hexdigest()[:8]
        bot_name = BOT_USERNAME.replace("@", "").replace(".", "_").lower()
        
        # إنشاء اسمين مختلفين
        emoji_set_name = f"emoji{unique_hash}_by_{bot_name}"
        sticker_set_name = f"sticker{unique_hash}_by_{bot_name}"
        
        # تنظيف الأسماء
        emoji_set_name = sanitize_sticker_set_name(emoji_set_name)
        sticker_set_name = sanitize_sticker_set_name(sticker_set_name)
        
        # فحص حجم الملف الأصلي
        original_size_kb = os.path.getsize(original_path) / 1024
        print(f"Original file size: {original_size_kb:.1f}KB")
        
        # معالجة الملف
        processed_path = original_path
        
        if sticker.is_animated:
            # TGS جاهز من تليجرام نفسه بالفعل (بحدود 64KB) — مفيش أداة في
            # البوت تقدر تعيد ترميزه، فبنستخدمه زي ما هو من غير أي معالجة.
            pass
        elif sticker.is_video:
            # معالجة الفيديو للرموز المميزة
            await update.message.reply_text(LANGS[lang]["optimizing_video"])
            processed_path = process_video_to_webm_advanced(original_path, max_duration=3, max_size_kb=256)
        else:
            # معالجة الصورة للرموز المميزة
            if original_size_kb > 256:
                await update.message.reply_text(LANGS[lang]["compressing_file"])
                processed_path = compress_image_aggressive(original_path, 256)
        
        # فحص الحجم بعد المعالجة
        processed_size_kb = os.path.getsize(processed_path) / 1024
        print(f"Processed file size: {processed_size_kb:.1f}KB")
        
        with open(processed_path, "rb") as f:
            sticker_data = f.read()
            
            data_size_kb = len(sticker_data) / 1024
            print(f"Data size in memory: {data_size_kb:.1f}KB")
            
            if data_size_kb > 256 and not sticker.is_animated:
                await update.message.reply_text("⚠️ الملف كبير جداً حتى بعد الضغط، جاري محاولة ضغط إضافي...")
                
                if sticker.is_video:
                    # ضغط فيديو إضافي
                    more_compressed = compress_video_extreme(processed_path, 256)
                    if more_compressed != processed_path:
                        with open(more_compressed, "rb") as mf:
                            sticker_data = mf.read()
                        data_size_kb = len(sticker_data) / 1024
                        print(f"Extreme compressed size: {data_size_kb:.1f}KB")
                else:
                    # ضغط صورة إضافي
                    more_compressed = compress_image_aggressive(processed_path, 256)
                    if more_compressed != processed_path:
                        with open(more_compressed, "rb") as mf:
                            sticker_data = mf.read()
                        data_size_kb = len(sticker_data) / 1024
                        print(f"Extreme compressed size: {data_size_kb:.1f}KB")
            
            sticker_format = "animated" if sticker.is_animated else ("video" if sticker.is_video else "static")
            sticker_obj = InputSticker(
                sticker=sticker_data,
                emoji_list=["⭐"],  # إيموجي مميز
                format=sticker_format
            )
            
            # المحاولة 1: إنشاء كـ Custom Emoji
            try:
                await update.message.reply_text("✨ جاري إنشاء الرمزية المميزة...")
                
                await ctx.bot.create_new_sticker_set(
                    user_id=user_id,
                    name=emoji_set_name,
                    title=f"✨ رمزية مميزة {timestamp}",
                    stickers=[sticker_obj],
                    sticker_type="custom_emoji"
                )
                
                # حفظ الرابط في قاعدة البيانات
                save_sticker_link(user_id, emoji_set_name, f"رمزية مميزة {timestamp}", is_custom_emoji=True, is_video=sticker.is_video)
                
                # التحقق من وجود الحزمة بعد إنشائها
                await asyncio.sleep(2)  # انتظار بسيط
                
                success_msg = "✅ تم التحويل إلى رمزية مميزة بنجاح!\n\n"
                success_msg += f"📊 الحجم: {data_size_kb:.1f}KB\n\n"
                success_msg += f"🔗 الرابط:\n"
                success_msg += f"https://t.me/addstickers/{emoji_set_name}\n\n"
                success_msg += f"⚠️ ملاحظة: قد يستغرق الرابط بضع لحظات ليصبح فعالاً"
                
                kb = [
                    [IKB("✨ إضافة الرمزية المميزة", url=f"https://t.me/addstickers/{emoji_set_name}", style="primary")],
                    [copy_link_ikb(emoji_set_name, style="success")],
                    [IKB("📂 رموزي المميزة", callback_data="my_stickers", style="primary")],
                    [IKB("🔙 القائمة الرئيسية", callback_data="back_main", style="danger")]
                ]
                
                await update.message.reply_text(success_msg, reply_markup=InlineKeyboardMarkup(kb))
                
            except Exception as emoji_error:
                error_msg = str(emoji_error)
                print(f"Custom emoji creation failed: {error_msg}")
                
                # تحليل الخطأ
                if "Sticker_png_dimensions" in error_msg:
                    # محاولة إصلاح أبعاد PNG
                    print("PNG dimensions error, fixing image...")
                    
                    if not sticker.is_video and not sticker.is_animated:
                        with Image.open(processed_path) as img:
                            # تأكد من الأبعاد 100x100
                            if img.size != (100, 100):
                                img = img.resize((100, 100), Image.LANCZOS)
                            
                            # تحويل إلى RGBA
                            if img.mode != 'RGBA':
                                img = img.convert('RGBA')
                            
                            # حفظ الصورة المصححة
                            corrected_path = f"{tempfile.gettempdir()}/corrected_{uuid.uuid4().hex}.png"
                            img.save(corrected_path, "PNG", optimize=True)
                            
                            with open(corrected_path, "rb") as cf:
                                corrected_data = cf.read()
                                corrected_sticker = InputSticker(
                                    sticker=corrected_data,
                                    emoji_list=["⭐"],
                                    format="static"
                                )
                                
                                # إعادة المحاولة بالصورة المصححة
                                try:
                                    await ctx.bot.create_new_sticker_set(
                                        user_id=user_id,
                                        name=emoji_set_name,
                                        title=f"✨ رمزية مميزة {timestamp}",
                                        stickers=[corrected_sticker],
                                        sticker_type="custom_emoji"
                                    )
                                    
                                    save_sticker_link(user_id, emoji_set_name, f"رمزية مميزة {timestamp}", is_custom_emoji=True, is_video=False)
                                    
                                    success_msg = "✅ تم التحويل إلى رمزية مميزة بنجاح!\n\n"
                                    success_msg += f"🌟 مميزات الرمزية:\n"
                                    success_msg += f"• يمكن استخدامها في أي محادثة\n"
                                    success_msg += f"• تظهر كإيموجي خاص بك\n"
                                    success_msg += f"• جودة عالية ومميزة\n\n"
                                    success_msg += f"📊 الحجم: {len(corrected_data)/1024:.1f}KB\n\n"
                                    success_msg += f"🔗 رابط الرمزية المميزة:\n"
                                    success_msg += f"https://t.me/addstickers/{emoji_set_name}\n\n"
                                    success_msg += f"⚠️ ملاحظة: قد يستغرق الرابط بضع لحظات ليصبح فعالاً"
                                    
                                    kb = [
                                        [IKB("✨ إضافة الرمزية المميزة", url=f"https://t.me/addstickers/{emoji_set_name}", style="success")],
                                        [copy_link_ikb(emoji_set_name, style="primary")],
                                        [IKB("📂 رموزي المميزة", callback_data="my_stickers", style="success")],
                                        [IKB("🔙 القائمة الرئيسية", callback_data="back_main", style="danger")]
                                    ]
                                    
                                    await update.message.reply_text(success_msg, reply_markup=InlineKeyboardMarkup(kb))
                                    
                                    # تنظيف الملفات
                                    try:
                                        os.remove(corrected_path)
                                    except:
                                        pass
                                    
                                    return
                                    
                                except Exception as retry_error:
                                    print(f"Retry also failed: {retry_error}")
                                    # الاستمرار في المحاولة كاستيكر عادي
                
                if "File is too big" in error_msg:
                    await update.message.reply_text(f"❌ حجم الملف كبير جداً للرمزية المميزة ({data_size_kb:.1f}KB)\n\nجاري المحاولة كاستيكر عادي (حتى 512KB)...")
                else:
                    await update.message.reply_text(f"⚠️ خطأ في إنشاء الرمزية المميزة\n\n🔄 جاري المحاولة كاستيكر عادي...")
                
                # المحاولة 2: إنشاء كـ Regular Sticker
                try:
                    await update.message.reply_text("🎨 جاري إنشاء استيكر مميز بديل...")
                    
                    await ctx.bot.create_new_sticker_set(
                        user_id=user_id,
                        name=sticker_set_name,
                        title=f"🎨 استيكر مميز {timestamp}",
                        stickers=[sticker_obj],
                        sticker_type="regular"
                    )
                    
                    # حفظ الرابط في قاعدة البيانات
                    save_sticker_link(user_id, sticker_set_name, f"استيكر مميز {timestamp}", is_custom_emoji=False, is_video=sticker.is_video)
                    
                    alt_msg = "✨ تم إنشاء استيكر مميز بديل!\n\n"
                    alt_msg += f"📌 سبب عدم إنشاء رمزية مميزة:\n"
                    alt_msg += f"• {error_msg[:100]}\n\n"
                    alt_msg += f"✅ لكن لا تقلق! الاستيكر المميز:\n"
                    alt_msg += f"• حجم أكبر (حتى 512KB)\n"
                    alt_msg += f"• متوافق مع جميع الأجهزة\n"
                    alt_msg += f"• يمكن استخدامه في المحادثات\n\n"
                    alt_msg += f"📊 الحجم: {data_size_kb:.1f}KB\n\n"
                    alt_msg += f"🔗 رابط الاستيكر المميز:\n"
                    alt_msg += f"https://t.me/addstickers/{sticker_set_name}"
                    
                    kb = [
                        [IKB("🎨 إضافة الاستيكر المميز", url=f"https://t.me/addstickers/{sticker_set_name}", style="primary")],
                        [copy_link_ikb(sticker_set_name, style="success")],
                        [IKB("📂 استيكراتي", callback_data="my_stickers", style="primary")],
                        [IKB("🔄 محاولة أخرى", callback_data="sticker_to_emoji", style="success")]
                    ]
                    
                    await update.message.reply_text(alt_msg, reply_markup=InlineKeyboardMarkup(kb))
                    
                except Exception as sticker_error:
                    error_msg2 = str(sticker_error)
                    print(f"Sticker creation also failed: {error_msg2}")
                    
                    if "File is too big" in error_msg2:
                        await update.message.reply_text(
                            f"❌ الملف كبير جداً!\n\n"
                            f"📊 الحدود:\n"
                            f"• الرموز المميزة: 256KB\n"
                            f"• الاستيكرات العادية: 512KB\n\n"
                            f"📌 حجم ملفك: {data_size_kb:.1f}KB\n\n"
                            f"💡 نصائح:\n"
                            f"1. حاول باستيكر أصغر\n"
                            f"2. للفيديوهات: اجعل المدة 2-3 ثواني فقط\n"
                            f"3. للصور: تأكد من أن الخلفية شفافة"
                        )
                    elif "too many" in error_msg2.lower():
                        await update.message.reply_text(
                            "❌ لقد وصلت للحد الأقصى من حزم الاستيكرات!\n\n"
                            "📌 الحل:\n"
                            "1. اذهب إلى @stickers\n"
                            "2. احذف بعض الحزم القديمة\n"
                            "3. حاول مرة أخرى"
                        )
                    else:
                        await update.message.reply_text(
                            f"❌ حدث خطأ غير متوقع:\n\n"
                            f"{error_msg2[:150]}\n\n"
                            f"📞 للمساعدة: @{OWNER_USER}"
                        )
        
        # تنظيف الملفات المؤقتة
        for temp_file in [original_path, processed_path]:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
        
        if user_id in USER_DATA:
            USER_DATA[user_id].pop("awaiting", None)
        
    except Exception as e:
        error_msg = str(e)
        print(f"Enhanced sticker conversion error: {error_msg}")
        
        await update.message.reply_text(
            f"❌ حدث خطأ في التحويل:\n\n"
            f"السبب المحتمل:\n"
            f"1. الملف كبير جداً\n"
            f"2. مشكلة في تنسيق الملف\n"
            f"3. قيود تليجرام\n\n"
            f"الحلول المقترحة:\n"
            f"• حاول باستيكر أصغر حجماً\n"
            f"• تأكد من جودة الاستيكر\n"
            f"• جرب استيكر بسيط أولاً\n\n"
            f"📞 للمساعدة: @{OWNER_USER}"
        )

# ========== Add to verified set ==========
async def add_verified_sticker(update: Update, ctx: ContextTypes.DEFAULT_TYPE, 
                              path: str, lang: str, is_video: bool = False):
    """إضافة استيكر إلى الحزمة"""
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            user_id = update.callback_query.from_user.id
            chat_id = update.callback_query.message.chat_id
        elif hasattr(update, 'message') and update.message:
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
        elif hasattr(update, 'effective_user') and update.effective_user:
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id if update.effective_chat else user_id
        else:
            raise AttributeError("لا يمكن العثور على user_id")
    except:
        user_id = None
        chat_id = None
    
    if not user_id or not chat_id:
        try:
            if update.message:
                await update.message.reply_text(f"{LANGS[lang]['error']} لم يتم العثور على المستخدم")
        except:
            pass
        return
    
    try:
        timestamp = int(time.time())
        unique_hash = hashlib.md5(f"{user_id}{timestamp}".encode()).hexdigest()[:8]
        bot_name = BOT_USERNAME.replace("@", "").replace(".", "_").lower()
        
        # إنشاء اسمين مختلفين
        emoji_set_name = f"emoji{unique_hash}_by_{bot_name}"
        sticker_set_name = f"sticker{unique_hash}_by_{bot_name}"
        
        # تنظيف الأسماء
        emoji_set_name = sanitize_sticker_set_name(emoji_set_name)
        sticker_set_name = sanitize_sticker_set_name(sticker_set_name)
        
        # استخدام الاسم المناسب
        set_name = emoji_set_name  # للرموز المميزة
        
        # إرسال إشارة "جاري التحميل"
        try:
            await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
        except:
            pass
        
        with open(path, "rb") as f:
            sticker_data = f.read()
            
            # فحص الحجم النهائي
            data_size_kb = len(sticker_data) / 1024
            max_size = 256  # 256KB للرموز المميزة
            
            if data_size_kb > max_size:
                try:
                    await update.message.reply_text(f"❌ {LANGS[lang]['file_too_big_after_compression']} ({data_size_kb:.1f}KB)")
                except:
                    pass
                return
            
            sticker_format = "video" if is_video else "static"
            sticker = InputSticker(
                sticker=sticker_data,
                emoji_list=[CUSTOM_EMOJIS[0]],
                format=sticker_format
            )
            
            title = f"✨ {timestamp}"
            
            # محاولة إنشاء كعلامة توثيق (custom_emoji)
            try:
                await ctx.bot.create_new_sticker_set(
                    user_id=user_id,
                    name=set_name,
                    title=title,
                    stickers=[sticker],
                    sticker_type="custom_emoji"
                )
                
                # حفظ الرابط في قاعدة البيانات
                save_sticker_link(user_id, set_name, title, is_custom_emoji=True, is_video=is_video)
                
                # انتظار بسيط لضمان تسجيل الحزمة
                await asyncio.sleep(2)
                
                sticker_type_text = "رمزية مميزة" if is_video else "رمزية ثابتة"
                
            except Exception as custom_error:
                print(f"Custom emoji error: {custom_error}")
                # محاولة كاستيكر عادي
                try:
                    await ctx.bot.create_new_sticker_set(
                        user_id=user_id,
                        name=sticker_set_name,
                        title=title,
                        stickers=[sticker],
                        sticker_type="regular"
                    )
                    
                    # حفظ الرابط في قاعدة البيانات
                    save_sticker_link(user_id, sticker_set_name, title, is_custom_emoji=False, is_video=is_video)
                    
                    set_name = sticker_set_name
                    sticker_type_text = "استيكر متحرك" if is_video else "استيكر ثابت"
                except Exception as regular_error:
                    print(f"Regular sticker error: {regular_error}")
                    await update.message.reply_text(f"{LANGS[lang]['error']} فشل في إنشاء الاستيكر. يرجى المحاولة مرة أخرى.")
                    return
        
        # إنشاء الرسالة النهائية
        success_msg = f"✅ تم إنشاء {sticker_type_text} بنجاح!\n\n"
        success_msg += f"🔗 رابط الحزمة:\nhttps://t.me/addstickers/{set_name}\n\n"
        success_msg += f"📌 للحفظ: اضغط على الرابط ثم انسخه\n\n"
        success_msg += f"⚠️ ملاحظة مهمة:\n"
        success_msg += f"• يمكن أن يستغرق الرابط بضع لحظات ليصبح فعالاً\n"
        success_msg += f"• تأكد من أنك تضغط على الرابط من نفس الجهاز"
        
        # إنشاء كيبورد مع زر الرابط
        kb = [
            [IKB(LANGS[lang]["open_link"], url=f"https://t.me/addstickers/{set_name}", style="primary")],
            [copy_link_ikb(set_name, style="success")],
            [IKB(LANGS[lang]["my_stickers"], callback_data="my_stickers", style="primary")],
            [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
        ]
        
        try:
            # إرسال الرسالة كرسالة جديدة
            msg = await ctx.bot.send_message(
                chat_id=chat_id,
                text=success_msg,
                reply_markup=InlineKeyboardMarkup(kb),
                disable_web_page_preview=False
            )
            
        except Exception as msg_error:
            print(f"Error sending message: {msg_error}")
            # محاولة بديلة
            try:
                if update.message:
                    await update.message.reply_text(
                        success_msg,
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
            except:
                pass
        
        # تنظيف الملف المؤقت
        try:
            os.remove(path)
        except:
            pass
        
        # إزالة حالة الانتظار
        if user_id in USER_DATA:
            USER_DATA[user_id].pop("awaiting", None)
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error creating sticker set: {error_msg}")
        
        if "stickerset_invalid" in error_msg.lower():
            error_msg = "اسم الحزمة غير مقبول من تليجرام. جاري المحاولة باسم آخر..."
        elif "too many" in error_msg.lower():
            error_msg = "لقد وصلت للحد الأقصى من حزم الاستيكرات (3 حزم لكل مستخدم)."
        elif "File is too big" in error_msg:
            error_msg = "حجم الملف كبير جداً! حاول بملف أصغر."
        
        try:
            if update.message:
                await update.message.reply_text(f"{LANGS[lang]['error']} {error_msg}")
        except:
            pass

# ========== Verify Sticker Set Handler - FIXED VERSION ==========
async def verify_sticker_set(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """التحقق من حزمة الاستيكرات - نسخة مصححة"""
    q = update.callback_query
    await q.answer()
    
    set_name = q.data.replace("verify_", "")
    
    # تأكد من أن set_name ليس فارغاً
    if not set_name or set_name == "verify_":
        await smart_edit(q, "❌ اسم الحزمة غير صالح")
        return
    
    try:
        # إنشاء رابط الحزمة
        link = f"https://t.me/addstickers/{set_name}"
        
        success_msg = "✅ تم إنشاء حزمة الاستيكرات!\n\n"
        success_msg += f"🔗 رابط الحزمة:\n{link}\n\n"
        success_msg += "📌 للحفظ: اضغط على الرابط ثم انسخه\n\n"
        success_msg += "⚠️ ملاحظة مهمة:\n"
        success_msg += "• يمكن أن يستغرق الرابط بضع لحظات ليصبح فعالاً\n"
        success_msg += "• تأكد من أنك تضغط على الرابط من نفس الجهاز"
        
        kb = [
            [IKB("🔗 افتح الرابط مباشرة", url=link, style="success")],
            [copy_link_ikb(set_name, style="primary")],
            [IKB("🔙 القائمة الرئيسية", callback_data="back_main", style="danger")]
        ]
        
        await smart_edit(q, success_msg, reply_markup=InlineKeyboardMarkup(kb))
        
    except Exception as e:
        error_msg = "❌ حدث خطأ في عرض التفاصيل\n\n"
        error_msg += f"🔗 رابط الحزمة:\nhttps://t.me/addstickers/{set_name}\n\n"
        error_msg += "⚠️ حاول فتح الرابط مباشرة"
        
        kb = [
            [IKB("🔗 افتح الرابط مباشرة", url=f"https://t.me/addstickers/{set_name}", style="success")],
            [IKB("🔙 القائمة الرئيسية", callback_data="back_main", style="danger")]
        ]
        
        await smart_edit(q, error_msg, reply_markup=InlineKeyboardMarkup(kb))

# ========== معلومات الاشتراك ==========
async def my_subscription_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات اشتراك المستخدم"""
    q = update.callback_query
    await q.answer()
    
    user_id = q.from_user.id
    lang = get_user_lang(user_id)
    
    sub_info = get_user_subscription_info(user_id)
    
    if sub_info["active"]:
        message_text = f"⭐ معلومات اشتراكك المميز:\n\n"
        message_text += f"✅ {LANGS[lang]['subscription_active']}\n"
        message_text += f"📦 الباقة: {sub_info['plan']}\n"
        message_text += f"📅 {LANGS[lang]['expiry_date']} {sub_info['expiry_date']}\n"
        message_text += f"⏳ {LANGS[lang]['days_remaining']} {sub_info['days_left']}\n\n"
        message_text += "✨ يمكنك استخدام جميع الميزات!"
    else:
        message_text = f"🔒 اشتراكك:\n\n"
        message_text += f"❌ {LANGS[lang]['subscription_expired']}\n\n"
        message_text += "💡 لتفعيل الاشتراك اضغط على زر الاشتراك أدناه"
    
    kb = [
        [IKB("🔄 تحديث", callback_data="my_subscription", style="primary")],
        [IKB(LANGS[lang]["subscribe"], callback_data="subscribe", style="success")],
        [IKB(LANGS[lang]["back"], callback_data="back_main", style="danger")]
    ]
    
    await smart_edit(q, message_text, reply_markup=InlineKeyboardMarkup(kb))

# ========== Error Handler ==========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج الأخطاء"""
    import telegram
    
    error = context.error
    
    # تجاهل أخطاء CallbackQuery القديمة
    if isinstance(error, telegram.error.BadRequest):
        error_msg = str(error)
        if "Query is too old" in error_msg or "response timeout expired" in error_msg:
            print(f"⚠️ تجاهل CallbackQuery قديم: {error_msg}")
            return
    
    print(f"❌ خطأ: {error}")
    
    # طباعة الـ Traceback فقط للأخطاء الحقيقية
    if not isinstance(error, telegram.error.BadRequest):
        traceback.print_exc()
    
    if isinstance(update, Update) and update.effective_message:
        try:
            lang = "ar"
            
            if update.effective_user:
                user_id = update.effective_user.id
                lang = get_user_lang(user_id)
            
            # إرسال رسالة خطأ فقط إذا لم تكن خطأ CallbackQuery قديم
            if not isinstance(error, telegram.error.BadRequest) or ("Query is too old" not in str(error)):
                error_msg = f"{LANGS[lang]['error']} حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى."
                
                if len(str(error)) > 100:
                    error_msg = f"{LANGS[lang]['error']} حدث خطأ في المعالجة."
                
                await update.effective_message.reply_text(error_msg)
                
                await asyncio.sleep(2)
                if update.effective_user:
                    await return_to_main_menu(update, context, lang, update.effective_user.id)
            
        except Exception as e:
            print(f"Error in error handler: {e}")

# ========== Cancel Handler ==========
async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إلغاء العملية الحالية"""
    user_id = update.effective_user.id
    lang = get_user_lang(user_id)
    
    if user_id in USER_DATA:
        USER_DATA[user_id].pop("awaiting", None)
    
    await update.message.reply_text("✅ تم الإلغاء")
    await return_to_main_menu(update, ctx, lang, user_id)
    
    return ConversationHandler.END

# ========== No Operation Handler ==========
async def noop_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالج للزر الذي لا يفعل شيئاً"""
    q = update.callback_query
    await q.answer()

# ========== تشغيل تلقائي لتفريغ الاستخدام اليومي ==========
async def reset_usage_daily():
    """تفريغ الاستخدام اليومي كل يوم"""
    while True:
        try:
            now = time.localtime()
            # تفريغ في منتصف الليل
            if now.tm_hour == 0 and now.tm_min == 0:
                reset_daily_usage()
                print(f"✅ تم تفريغ الاستخدام اليومي في {time.strftime('%Y-%m-%d %H:%M')}")
            await asyncio.sleep(60)  # التحقق كل دقيقة
        except Exception as e:
            print(f"Error in reset_usage_daily: {e}")
            await asyncio.sleep(300)

# ========== Main ==========
def main():
    """الدالة الرئيسية لتشغيل البوت"""
    init_db()
    
    try:
        # ضبط الـ timeouts هنا وقت بناء الـ Application (مش فى run_polling) عشان
        # يشتغل مع كل نسخ المكتبة: من v22.0 اتشالت هذه الباراميترات من run_polling
        # ولازم تتضبط عبر ApplicationBuilder بدالها.
        builder = Application.builder().token(BOT_TOKEN)
        for method_name in (
            "get_updates_read_timeout", "get_updates_write_timeout",
            "get_updates_connect_timeout", "get_updates_pool_timeout",
        ):
            method = getattr(builder, method_name, None)
            if method is not None:
                try:
                    builder = method(60)
                except Exception:
                    pass
        app = builder.build()
        
        # محادثة الأدمن
        admin_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(admin_add_subscription, pattern="^admin_add_sub$"),
                CallbackQueryHandler(admin_remove_subscription, pattern="^admin_remove_sub$"),
                CallbackQueryHandler(admin_search_user, pattern="^admin_search_user$")
            ],
            states={
                "ADMIN_USER_ID": [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_user_id)
                ],
                "ADMIN_CHOOSE_PLAN": [
                    CallbackQueryHandler(handle_admin_choose_plan, pattern="^admin_plan_")
                ]
            },
            fallbacks=[
                CallbackQueryHandler(subscription_management, pattern="^subscription_management$"),
                CallbackQueryHandler(admin_menu, pattern="^admin_menu$"),
                CommandHandler("cancel", cancel)
            ],
            allow_reentry=True
        )
        
        # محادثة البث
        broadcast_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(admin_broadcast, pattern="^admin_broadcast$")],
            states={
                BROADCAST_MODE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message),
                    CallbackQueryHandler(confirm_broadcast, pattern="^(confirm_broadcast|cancel_broadcast)$")
                ]
            },
            fallbacks=[
                CallbackQueryHandler(admin_menu, pattern="^admin_menu$"),
                CommandHandler("cancel", cancel)
            ],
            allow_reentry=True
        )
        
        conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(send_text, "send_text"),
                CallbackQueryHandler(photo_callback, "send_photo")
            ],
            states={
                TEXT_RECEIVED: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, text_received),
                    MessageHandler(filters.PHOTO, handle_photo)
                ],
                TEXT_ARRANGEMENT: [CallbackQueryHandler(text_arrangement_choice, pattern="^arrangement_")],
                REMOVE_BG_CHOICE: [CallbackQueryHandler(remove_bg_choice, pattern="^remove_bg_")],
                FONT_CHOICE: [CallbackQueryHandler(font_choice, pattern="^font_")],
                STYLE_CHOICE: [CallbackQueryHandler(style_choice, pattern="^style_")],
                EFFECT_CHOICE: [CallbackQueryHandler(effect_choice, pattern="^effect_|^finish_effects$")],
                COLOR_CHOICE: [CallbackQueryHandler(color_choice, pattern="^color_|^dual1_|^dual2_")],
                EMOJI_CHOICE: [CallbackQueryHandler(emoji_choice, pattern="^emoji_")],
                STICKER_TYPE_CHOICE: [CallbackQueryHandler(sticker_type_choice, pattern="^stickertype_")],
                BROADCAST_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)]
            },
            fallbacks=[
                CallbackQueryHandler(back_main, "back_main"),
                CommandHandler("cancel", cancel),
                MessageHandler(filters.COMMAND, cancel)
            ],
            allow_reentry=True
        )
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("cancel", cancel))
        app.add_handler(CommandHandler("help", start))
        
        # معالجات CallbackQuery
        app.add_handler(CallbackQueryHandler(set_lang, pattern="^lang_"))
        app.add_handler(CallbackQueryHandler(check_sub, "check_sub"))
        app.add_handler(CallbackQueryHandler(change_lang, "change_lang"))
        app.add_handler(CallbackQueryHandler(subscribe_menu, "subscribe"))
        app.add_handler(CallbackQueryHandler(handle_payment, pattern="^pay_"))
        app.add_handler(CallbackQueryHandler(toggle_subscription, "toggle_sub"))
        app.add_handler(CallbackQueryHandler(back_main, "back_main"))
        app.add_handler(CallbackQueryHandler(video_callback, "send_video"))
        app.add_handler(CallbackQueryHandler(animated_callback, "send_animated"))
        app.add_handler(CallbackQueryHandler(regular_sticker_callback, "send_regular_sticker"))
        app.add_handler(CallbackQueryHandler(sticker_to_emoji_callback, "sticker_to_emoji"))
        app.add_handler(CallbackQueryHandler(my_stickers_menu, "my_stickers"))
        app.add_handler(CallbackQueryHandler(handle_sticker_page, pattern="^stickers_page_"))
        app.add_handler(CallbackQueryHandler(handle_copy_link, pattern="^copy_"))
        app.add_handler(CallbackQueryHandler(admin_menu, "admin_menu"))
        app.add_handler(CallbackQueryHandler(admin_stats, "admin_stats"))
        app.add_handler(CallbackQueryHandler(admin_broadcast, "admin_broadcast"))
        app.add_handler(CallbackQueryHandler(verify_sticker_set, pattern="^verify_"))
        app.add_handler(CallbackQueryHandler(noop_handler, "noop"))
        
        # إضافة معالجات الأدمن الجديدة
        app.add_handler(CallbackQueryHandler(subscription_management, pattern="^subscription_management$"))
        app.add_handler(CallbackQueryHandler(admin_view_subscribers, pattern="^admin_view_subs$"))
        app.add_handler(CallbackQueryHandler(admin_subscription_stats, pattern="^admin_sub_stats$"))
        app.add_handler(CallbackQueryHandler(my_subscription_info, pattern="^my_subscription$"))
        
        app.add_handler(admin_conv)
        app.add_handler(broadcast_conv)
        
        # إضافة معالج المحادثة
        app.add_handler(conv)
        
        # معالجات الوسائط
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.VIDEO, handle_video))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_animated))
        app.add_handler(MessageHandler(filters.ANIMATION, handle_animated))
        app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker_enhanced))
        
        # معالج الاستيكر العادى (غير المميز) - مجموعة منفصلة لأنه يتحقق من حالة الانتظار بنفسه
        app.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.Document.ALL,
            handle_regular_sticker_media
        ), group=1)
        
        # معالج الأخطاء
        app.add_error_handler(error_handler)
        
        # تشغيل البوت مع المهمة الخلفية
        import asyncio
        loop = asyncio.get_event_loop()
        loop.create_task(reset_usage_daily())
        
        # تشغيل البوت
        print("=" * 50)
        print("🤖 بوت إنشاء الاستيكرات المميزة يعمل الآن...")
        print(f"📞 للتواصل: @{OWNER_USER}")
        print(f"👥 عدد الأدمن: {len(ADMIN_IDS)}")
        print(f"🌐 اللغات المدعومة: {len(LANGS)}")
        print(f"😊 الإيموجيات المتاحة: {len(CUSTOM_EMOJIS)}")
        print(f"🎨 التأثيرات الجديدة: 3D مباني، كريستال، انعكاس مائي")
        print(f"🕌 الخطوط العربية: خط الثلث، النسخ، الديواني، الرقعة")
        print(f"🏰 الخطوط الإنجليزية: قوطي، متصل، حديث")
        print(f"🌺 الزخارف: عربية تقليدية، إنجليزية فاخرة")
        print(f"💰 نظام الاشتراكات: {'🟢 مفعل' if SUBSCRIPTION_ENABLED else '🔴 معطل'}")
        print(f"📦 خطط الاشتراك: {len(SUBSCRIPTION_PLANS)} خطط")
        print(f"📊 نظام الاستخدام: 3 مرات يومياً للمجاني | غير محدود للمشتركين")
        print("=" * 50)
        
        # نستخدم فقط الباراميترات المدعومة فعلياً فى نسخة run_polling المثبتة،
        # عشان نتجنب "unexpected keyword argument" فى النسخ الحديثة (v22+)
        _run_polling_kwargs = {
            "allowed_updates": Update.ALL_TYPES,
            "drop_pending_updates": True,
        }
        _legacy_timeout_kwargs = {
            "read_timeout": 60, "write_timeout": 60,
            "connect_timeout": 60, "pool_timeout": 60,
        }
        try:
            _rp_params = _inspect.signature(app.run_polling).parameters
            for k, v in _legacy_timeout_kwargs.items():
                if k in _rp_params:
                    _run_polling_kwargs[k] = v
        except Exception:
            pass

        app.run_polling(**_run_polling_kwargs)
        
    except Exception as e:
        print(f"❌ خطأ فادح في تشغيل البوت: {e}")
        traceback.print_exc()
        print("🔄 إعادة تشغيل البوت بعد 10 ثواني...")
        time.sleep(10)
        main()  # إعادة التشغيل

if __name__ == "__main__":
    main()