"""
Karta-pack Telegram bot v2 (aiogram 3.x)

O'rnatish:   pip install "aiogram>=3.7" pillow
Ishga tushirish (Windows PowerShell):
    $env:BOT_TOKEN="123:ABC"
    $env:ADMIN_IDS="123456789"
    $env:PIXABAY_KEY="pixabay kaliti"     # ixtiyoriy, bo'lmasa gradient fon
    python card_bot_v2.py

Eslatma: eski cards.db dagi kartalar yangi ro'yxatga mos kelmaydi,
shuning uchun eski cards.db ni o'chirib, yangidan boshlang.
"""
import asyncio
import html
import io
import logging
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile, CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, KeyboardButton, LabeledPrice, Message,
    PreCheckoutQuery, ReplyKeyboardMarkup,
)
from PIL import Image, ImageDraw, ImageFont, ImageOps

if load_dotenv is not None:
    load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PIXABAY_KEY = os.getenv("PIXABAY_KEY", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()}

LEGENDARY_PRIZE = 200      # Stars (admin qo'lda beradi)
EPIC_SET_SIZE = 5          # nechta epik karta yig'ilsa
EPIC_SET_PRIZE = 150       # Stars (admin qo'lda beradi)

# ---------------------------------------------------------------- packlar
# weights: oddiy / kam uchraydigan / epik (foiz). Afsonaviy faqat admin sovg'asi.
PACKS = {
    "free": {"emoji": "🎴", "title": "Bepul pack", "price": 0,
             "w": {"common": 91.5, "rare": 8.0, "epic": 0.5}},
    "p30": {"emoji": "🥉", "title": "Bronza pack", "price": 30,
            "w": {"common": 78.0, "rare": 20.0, "epic": 2.0}},
    "p50": {"emoji": "🥈", "title": "Kumush pack", "price": 50,
            "w": {"common": 66.0, "rare": 30.0, "epic": 4.0}},
    "p70": {"emoji": "🥇", "title": "Oltin pack", "price": 70,
            "w": {"common": 53.0, "rare": 40.0, "epic": 7.0}},
    "p100": {"emoji": "💎", "title": "Brilliant pack", "price": 100,
             "w": {"common": 40.0, "rare": 50.0, "epic": 10.0}},
}

# ---------------------------------------------------------------- kartalar
CARDS = [
    # oddiy
    {"id": 1, "name": "Martin Odegaard", "rarity": "common", "rating": 84},
    {"id": 2, "name": "Alexis Mac Allister", "rarity": "common", "rating": 83},
    {"id": 3, "name": "Dominik Szoboszlai", "rarity": "common", "rating": 82},
    {"id": 4, "name": "Bruno Guimaraes", "rarity": "common", "rating": 83},
    {"id": 5, "name": "Ilkay Gundogan", "rarity": "common", "rating": 82},
    {"id": 6, "name": "Rodrygo", "rarity": "common", "rating": 84},
    {"id": 7, "name": "Cole Palmer", "rarity": "common", "rating": 84},
    {"id": 8, "name": "Declan Rice", "rarity": "common", "rating": 85},
    # kam uchraydigan
    {"id": 10, "name": "Phil Foden", "rarity": "rare", "rating": 86},
    {"id": 11, "name": "Bukayo Saka", "rarity": "rare", "rating": 87},
    {"id": 12, "name": "Jude Bellingham", "rarity": "rare", "rating": 88},
    {"id": 13, "name": "Federico Valverde", "rarity": "rare", "rating": 87},
    {"id": 14, "name": "Heung-Min Son", "rarity": "rare", "rating": 86},
    {"id": 15, "name": "Bernardo Silva", "rarity": "rare", "rating": 87},
    {"id": 16, "name": "Virgil van Dijk", "rarity": "rare", "rating": 88},
    # epik
    {"id": 20, "name": "Vinicius Jr", "rarity": "epic", "rating": 90},
    {"id": 21, "name": "Lamine Yamal", "rarity": "epic", "rating": 90},
    {"id": 22, "name": "Rodri", "rarity": "epic", "rating": 91},
    {"id": 23, "name": "Mohamed Salah", "rarity": "epic", "rating": 91},
    {"id": 24, "name": "Harry Kane", "rarity": "epic", "rating": 91},
    {"id": 25, "name": "Kevin De Bruyne", "rarity": "epic", "rating": 91},
    # afsonaviy
    {"id": 30, "name": "Lionel Messi", "rarity": "legendary", "rating": 96},
    {"id": 31, "name": "Cristiano Ronaldo", "rarity": "legendary", "rating": 95},
    {"id": 32, "name": "Kylian Mbappe", "rarity": "legendary", "rating": 97},
    {"id": 33, "name": "Erling Haaland", "rarity": "legendary", "rating": 97},
    {"id": 34, "name": "Pele", "rarity": "legendary", "rating": 98},
    {"id": 35, "name": "Diego Maradona", "rarity": "legendary", "rating": 98},
]

RARITY = {  # emoji, nom, gradient rang 1, gradient rang 2, Pixabay qidiruvi
    "common": ("⚪", "Oddiy", (120, 200, 255), (40, 90, 200), "football stadium"),
    "rare": ("🔵", "Kam uchraydigan", (60, 255, 170), (0, 130, 110), "soccer ball fire"),
    "epic": ("🟣", "Epik", (255, 90, 220), (90, 20, 170), "football neon lights"),
    "legendary": ("🟡", "Afsonaviy", (255, 235, 90), (255, 110, 0), "golden trophy fireworks"),
}

BY_ID = {c["id"]: c for c in CARDS}
BY_RARITY = {r: [c for c in CARDS if c["rarity"] == r] for r in RARITY}

# ---------------------------------------------------------------- baza
db = sqlite3.connect("cards.db", check_same_thread=False)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, name TEXT, last_free TEXT DEFAULT '',
    packs INTEGER DEFAULT 0, gift INTEGER DEFAULT 0, epic_rewarded INTEGER DEFAULT 0,
    ref_by INTEGER DEFAULT NULL, bonus_packs INTEGER DEFAULT 0,
    team TEXT DEFAULT '', team_score INTEGER DEFAULT 0,
    last_team_reward TEXT DEFAULT '', invite_bonus_given INTEGER DEFAULT 0,
    gift_pack_key TEXT DEFAULT 'free');
CREATE TABLE IF NOT EXISTS cards(
    user_id INTEGER, card_id INTEGER, cnt INTEGER DEFAULT 0,
    PRIMARY KEY(user_id, card_id));
CREATE TABLE IF NOT EXISTS prizes(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
    reason TEXT, done INTEGER DEFAULT 0);
""")


def ensure_schema():
    existing = {r[1] for r in db.execute("PRAGMA table_info(users)").fetchall()}
    for col, stmt in {
        "ref_by": "ref_by INTEGER DEFAULT NULL",
        "bonus_packs": "bonus_packs INTEGER DEFAULT 0",
        "team": "team TEXT DEFAULT ''",
        "team_score": "team_score INTEGER DEFAULT 0",
        "last_team_reward": "last_team_reward TEXT DEFAULT ''",
        "invite_bonus_given": "invite_bonus_given INTEGER DEFAULT 0",
        "gift_pack_key": "gift_pack_key TEXT DEFAULT 'free'",
    }.items():
        if col not in existing:
            db.execute(f"ALTER TABLE users ADD COLUMN {stmt}")
    db.commit()


ensure_schema()


def q(sql, args=(), one=False, commit=False):
    cur = db.execute(sql, args)
    if commit:
        db.commit()
    return cur.fetchone() if one else cur.fetchall()


def today():
    return (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%d")


def is_admin(uid):
    return uid in ADMIN_IDS


def mention(uid, name):
    return f'<a href="tg://user?id={uid}">{html.escape(name or str(uid))}</a>'


def pack_label(key):
    return PACKS.get(key, {}).get("title", key)


def sum_team_score(team_ids):
    total = 0
    for cid in team_ids:
        card = BY_ID.get(int(cid))
        if not card:
            continue
        mult = {"common": 1, "rare": 2, "epic": 4, "legendary": 6}[card["rarity"]]
        total += card["rating"] * mult
    return total


def current_month_key():
    return (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m")


def add_bonus_packs(uid, count):
    q("UPDATE users SET bonus_packs = bonus_packs + ? WHERE id=?", (count, uid), commit=True)


def parse_ref_from_text(text):
    if not text:
        return None
    s = text.strip().split()
    if len(s) >= 2 and s[1].isdigit():
        return int(s[1])
    return None


def inventory_cards(uid):
    rows = q("SELECT card_id, cnt FROM cards WHERE user_id=?", (uid,))
    return {r["card_id"]: r["cnt"] for r in rows if r["card_id"] in BY_ID}


def merge_duplicate_cards(uid):
    have = inventory_cards(uid)
    merged = []
    for card_id, cnt in list(have.items()):
        card = BY_ID.get(card_id)
        if not card or cnt < 3:
            continue
        while cnt >= 3:
            cnt -= 3
            rarity_order = ["common", "rare", "epic", "legendary"]
            cur_idx = rarity_order.index(card["rarity"])
            target_rarity = rarity_order[min(cur_idx + 1, len(rarity_order) - 1)]
            if target_rarity == card["rarity"]:
                target = random.choice(BY_RARITY[card["rarity"]])
            else:
                target = random.choice(BY_RARITY[target_rarity])
            q("UPDATE cards SET cnt = cnt - 3 WHERE user_id=? AND card_id=?", (uid, card_id), commit=True)
            q("INSERT INTO cards(user_id, card_id, cnt) VALUES(?,?,1) "
              "ON CONFLICT(user_id, card_id) DO UPDATE SET cnt = cnt + 1",
              (uid, target["id"]), commit=True)
            q("UPDATE users SET team='' WHERE id=?", (uid,), commit=True)
            merged.append({"from": card["rarity"], "to": target_rarity, "card": target["name"], "pack": target_rarity})
        have[card_id] = cnt
    return merged


def build_team(uid):
    have = inventory_cards(uid)
    if not have:
        return [], 0
    team_ids = []
    for card_id in sorted(have, key=lambda cid: (BY_ID[cid]["rating"], BY_ID[cid]["rarity"]), reverse=True):
        if have[card_id] > 0 and len(team_ids) < 5:
            team_ids.append(str(card_id))
    score = sum_team_score(team_ids)
    q("UPDATE users SET team=?, team_score=? WHERE id=?", (",".join(team_ids), score, uid), commit=True)
    return team_ids, score


def month_reward_if_needed(uid):
    user = q("SELECT team_score, last_team_reward FROM users WHERE id=?", (uid,), one=True)
    month = current_month_key()
    if not user or user["team_score"] <= 0:
        return 0
    if user["last_team_reward"] == month:
        return 0
    rows = q("SELECT id, team_score, name FROM users WHERE team_score > 0 ORDER BY team_score DESC LIMIT 1",)
    if not rows:
        return 0
    winner = rows[0]
    if winner["id"] == uid:
        q("UPDATE users SET last_team_reward=? WHERE id=?", (month, uid), commit=True)
        q("INSERT INTO prizes(user_id, amount, reason, done) VALUES(?,?,?,1)", (uid, 200, f"Futbol jamoa reytingi: {month}"), commit=True)
        return 200
    return 0


def odds_text():
    lines = ["📊 <b>Pack ehtimollari</b>\n"]
    for p in PACKS.values():
        price = f"{p['price']} Stars" if p["price"] else "bepul"
        w = p["w"]
        lines.append(f"{p['emoji']} <b>{p['title']}</b> ({price})\n"
                     f"   ⚪ {w['common']}%  🔵 {w['rare']}%  🟣 {w['epic']}%")
    lines.append("\n🟡 Afsonaviy karta packdan tushmaydi — faqat eng faol o'yinchilarga "
                 "admin sovg'asi sifatida beriladi.")
    return "\n".join(lines)


# ---------------------------------------------------------------- rasm
os.makedirs("bg", exist_ok=True)
_img_cache, _bg, _bg_done, _hits = {}, {}, set(), {}


def _font(size):
    for f in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


async def ensure_bg(card):
    """Pixabay'dan fon rasmini yuklab, diskka saqlaydi (bir marta)."""
    cid = card["id"]
    if cid in _bg_done or not PIXABAY_KEY:
        return
    _bg_done.add(cid)
    path = f"bg/{cid}.jpg"
    try:
        if os.path.exists(path):
            _bg[cid] = open(path, "rb").read()
        else:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                hits = _hits.get(card["rarity"])
                if hits is None:
                    params = {"key": PIXABAY_KEY, "q": RARITY[card["rarity"]][4],
                              "image_type": "photo", "orientation": "vertical",
                              "safesearch": "true", "per_page": 50}
                    async with s.get("https://pixabay.com/api/", params=params) as r:
                        hits = (await r.json()).get("hits", [])
                    _hits[card["rarity"]] = hits
                if not hits:
                    return
                async with s.get(hits[cid % len(hits)]["webformatURL"]) as r:
                    data = await r.read()
            open(path, "wb").write(data)
            _bg[cid] = data
        _img_cache.pop(cid, None)
    except Exception:
        logging.exception("Pixabay fon yuklanmadi")


def card_image(card):
    if card["id"] in _img_cache:
        return _img_cache[card["id"]]
    _, label, c1, c2, _q = RARITY[card["rarity"]]
    W, H = 600, 800
    grad = Image.new("RGB", (W, H))
    gd = ImageDraw.Draw(grad)
    for y in range(H):
        t = y / H
        gd.line([(0, y), (W, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
    img = grad
    if card["id"] in _bg:
        try:
            bg = Image.open(io.BytesIO(_bg[card["id"]])).convert("RGB")
            bg = ImageOps.fit(bg, (W, H))
            img = Image.blend(bg, grad, 0.55)
        except Exception:
            img = grad
    img = img.convert("RGBA")

    # nur (rays) va qoraytirilgan pastki panel
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    cx, cy = 300, 400
    for i in range(16):
        a = i * (360 / 16)
        ld.pieslice((cx - 600, cy - 600, cx + 600, cy + 600), a, a + 11, fill=(255, 255, 255, 38))
    ld.rounded_rectangle((34, 570, W - 34, H - 34), radius=30, fill=(0, 0, 0, 120))
    img = Image.alpha_composite(img, layer).convert("RGB")
    d = ImageDraw.Draw(img)

    d.rounded_rectangle((18, 18, W - 18, H - 18), radius=40, outline=(255, 255, 255), width=8)
    d.rounded_rectangle((34, 34, W - 34, H - 34), radius=30, outline=(255, 255, 255), width=2)
    d.text((60, 55), str(card["rating"]), font=_font(110), fill=(255, 255, 255))
    d.text((64, 175), "OVR", font=_font(34), fill=(255, 255, 255))

    # markaziy doira + bosh harflar
    d.ellipse((150, 250, 450, 550), fill=(255, 255, 255), outline=c2, width=10)
    initials = "".join(w[0] for w in card["name"].split()[:2]).upper()
    f = _font(120)
    bb = d.textbbox((0, 0), initials, font=f)
    d.text((300 - (bb[2] - bb[0]) / 2 - bb[0], 400 - (bb[3] - bb[1]) / 2 - bb[1]),
           initials, font=f, fill=c2)

    name = card["name"].upper()
    f = _font(46)
    while d.textlength(name, font=f) > W - 100 and len(name) > 5:
        name = name[:-1]
    d.text(((W - d.textlength(name, font=f)) / 2, 600), name, font=f, fill=(255, 255, 255))
    f = _font(40)
    lab = label.upper()
    d.text(((W - d.textlength(lab, font=f)) / 2, 690), lab, font=f, fill=(255, 235, 120))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    _img_cache[card["id"]] = buf.getvalue()
    return _img_cache[card["id"]]


# ---------------------------------------------------------------- tugmalar
BTN_FREE = "🎴 Bepul pack"
BTN_SHOP = "⭐ Pack do'koni"
BTN_MY = "🃏 Mening kartalarim"
BTN_TOP = "🏆 Reyting"
BTN_ODDS = "📊 Ehtimollar"
BTN_BONUS = "🎁 Bonus pack"
BTN_TEAM = "👥 Jamoa"
BTN_MERGE = "🧩 Birlashtirish"
BTN_A_USERS = "👥 Foydalanuvchilar"
BTN_A_PACK = "🎁 Admin pack"
BTN_A_GIFT = "👑 Zo'r sovg'a berish"
BTN_A_PRIZES = "💰 Mukofotlar"
BTN_A_STATS = "📊 Statistika"
BTN_A_ACTIVE = "👥 Faol userlar"
BTN_A_BACK = "⬅️ Orqaga"


def admin_users_menu():
    rows = [[BTN_A_PACK, BTN_A_GIFT], [BTN_A_PRIZES, BTN_A_STATS], [BTN_A_ACTIVE, BTN_A_BACK]]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in r] for r in rows], resize_keyboard=True)


def menu(uid):
    if is_admin(uid):
        rows = [[BTN_A_USERS, BTN_MY], [BTN_A_GIFT, BTN_A_PRIZES], [BTN_A_STATS, BTN_A_ACTIVE]]
    else:
        rows = [[BTN_FREE, BTN_SHOP], [BTN_MY, BTN_TEAM], [BTN_ODDS, BTN_BONUS], [BTN_MERGE]]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in r] for r in rows], resize_keyboard=True)


def shop_kb():
    rows = [[InlineKeyboardButton(text=f"{p['emoji']} {p['title']} — {p['price']} ⭐",
                                  callback_data=f"buy:{k}")]
            for k, p in PACKS.items() if p["price"]]
    rows.append([InlineKeyboardButton(text="📊 Ehtimollarni ko'rish", callback_data="odds")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


router = Router()


def register(user):
    q("INSERT OR IGNORE INTO users(id, name) VALUES(?,?)", (user.id, user.full_name), commit=True)
    q("UPDATE users SET name=? WHERE id=?", (user.full_name, user.id), commit=True)


async def notify_admins(bot, text, markup=None):
    for a in ADMIN_IDS:
        try:
            await bot.send_message(a, text, reply_markup=markup)
        except Exception:
            logging.exception("Adminga xabar bormadi")


async def add_prize(bot, uid, amount, reason):
    q("INSERT INTO prizes(user_id, amount, reason) VALUES(?,?,?)", (uid, amount, reason), commit=True)
    pid = q("SELECT last_insert_rowid() AS i", one=True)["i"]
    u = q("SELECT name FROM users WHERE id=?", (uid,), one=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Berildi", callback_data=f"done:{pid}")]])
    await notify_admins(
        bot, f"💰 <b>Yangi mukofot!</b>\n{mention(uid, u['name'])} — <b>{amount} Stars</b>\nSabab: {reason}", kb)


# ---------------------------------------------------------------- pack ochish
def pick_card(uid, pack_key):
    u = q("SELECT gift, gift_pack_key FROM users WHERE id=?", (uid,), one=True)
    if u["gift"] and not is_admin(uid):
        chosen = u["gift_pack_key"] if u["gift_pack_key"] in PACKS else pack_key
        q("UPDATE users SET gift=0, gift_pack_key='free' WHERE id=?", (uid,), commit=True)
        if chosen in PACKS:
            w = PACKS[chosen]["w"]
            rarity = random.choices(list(w), weights=list(w.values()))[0]
            return random.choice(BY_RARITY[rarity])
        return random.choice(BY_RARITY["legendary"])
    w = PACKS[pack_key]["w"]
    rarity = random.choices(list(w), weights=list(w.values()))[0]
    return random.choice(BY_RARITY[rarity])


async def open_pack(bot, chat_id, uid, pack_key="free", count_pack=True):
    card = pick_card(uid, pack_key)
    await ensure_bg(card)
    q("INSERT INTO cards(user_id, card_id, cnt) VALUES(?,?,1) "
      "ON CONFLICT(user_id, card_id) DO UPDATE SET cnt = cnt + 1", (uid, card["id"]), commit=True)
    if count_pack:
        q("UPDATE users SET packs = packs + 1 WHERE id=?", (uid,), commit=True)

    emoji, label = RARITY[card["rarity"]][:2]
    caption = f"{emoji} <b>{html.escape(card['name'])}</b>\n{label} • ⭐ {card['rating']}"
    if card["rarity"] == "legendary":
        caption = "🔥🔥🔥 <b>ZO'R KARTA TUSHDI!</b> 🔥🔥🔥\n\n" + caption + \
                  f"\n\n💰 Mukofot: <b>{LEGENDARY_PRIZE} Stars</b>! Admin siz bilan bog'lanadi."
    elif card["rarity"] == "epic":
        caption = "✨ <b>EPIK KARTA!</b> ✨\n\n" + caption

    await bot.send_photo(chat_id, BufferedInputFile(card_image(card), "card.png"), caption=caption)

    if is_admin(uid):
        return
    if card["rarity"] == "legendary":
        await add_prize(bot, uid, LEGENDARY_PRIZE, f"Zo'r karta: {card['name']}")
    if card["rarity"] == "epic":
        ids = ",".join(str(c["id"]) for c in BY_RARITY["epic"])
        total = q(f"SELECT COALESCE(SUM(cnt),0) AS s FROM cards WHERE user_id=? AND card_id IN ({ids})",
                  (uid,), one=True)["s"]
        rewarded = q("SELECT epic_rewarded FROM users WHERE id=?", (uid,), one=True)["epic_rewarded"]
        if total // EPIC_SET_SIZE > rewarded:
            q("UPDATE users SET epic_rewarded=? WHERE id=?", (total // EPIC_SET_SIZE, uid), commit=True)
            await bot.send_message(
                chat_id, f"🎉 <b>{EPIC_SET_SIZE} ta epik karta yig'dingiz!</b>\n"
                         f"💰 Mukofot: <b>{EPIC_SET_PRIZE} Stars</b>! Admin siz bilan bog'lanadi.")
            await add_prize(bot, uid, EPIC_SET_PRIZE, f"{EPIC_SET_SIZE} ta epik karta yig'di")


# ---------------------------------------------------------------- foydalanuvchi
@router.message(CommandStart())
async def start(m: Message):
    register(m.from_user)
    ref_by = parse_ref_from_text(m.text)
    if ref_by and ref_by != m.from_user.id:
        u = q("SELECT ref_by, invite_bonus_given FROM users WHERE id=?", (m.from_user.id,), one=True)
        if not u or u["ref_by"] is None:
            q("UPDATE users SET ref_by=? WHERE id=?", (ref_by, m.from_user.id), commit=True)
            ref_user = q("SELECT id FROM users WHERE id=?", (ref_by,), one=True)
            if ref_user:
                q("UPDATE users SET bonus_packs = bonus_packs + 5 WHERE id=?", (ref_by,), commit=True)
                q("UPDATE users SET invite_bonus_given=1 WHERE id=?", (ref_by,), commit=True)
                try:
                    await m.bot.send_message(ref_by, "🎁 <b>Taklifingiz ishladi!</b>\nSizga 4 ta bonus pack berildi.")
                except Exception:
                    pass
    text = (f"👋 Salom, <b>{html.escape(m.from_user.first_name)}</b>!\n\n"
            "⚽ Mashhur futbolchilar kartalari botiga xush kelibsiz!\n"
            "🎴 Kuniga 1 ta <b>bepul pack</b>\n"
            "🎁 Taklif qilganingizda <b>5 ta bonus pack</b> olasiz\n"
            "⭐ Pack do'konida 30 / 50 / 70 / 100 Stars li packlar — qimmatrog'ida zo'r karta ehtimoli yuqori\n"
            f"🟣 {EPIC_SET_SIZE} ta epik karta yig'sangiz — <b>{EPIC_SET_PRIZE} Stars</b> mukofot\n"
            "👑 Eng faol o'yinchilarga admin <b>afsonaviy karta</b> sovg'a qiladi "
            f"(<b>{LEGENDARY_PRIZE} Stars</b> mukofot bilan)!\n\n"
            "📊 Barcha ehtimollar ochiq: «Ehtimollar» tugmasini bosing.\n"
            "🧩 3 ta bir xil karta birga kelganda yuqori darajaga o‘tadi.\n"
            "👥 /team buyrug'i bilan jamoa yig'ishingiz mumkin.")
    await m.answer(text, reply_markup=menu(m.from_user.id))


@router.message(F.text == BTN_ODDS)
async def odds_msg(m: Message):
    await m.answer(odds_text())


@router.callback_query(F.data == "odds")
async def odds_cb(c: CallbackQuery):
    await c.message.answer(odds_text())
    await c.answer()


@router.message(F.text == BTN_FREE)
async def free_pack(m: Message, bot: Bot):
    register(m.from_user)
    u = q("SELECT last_free, bonus_packs FROM users WHERE id=?", (m.from_user.id,), one=True)
    if u["bonus_packs"] > 0:
        q("UPDATE users SET bonus_packs = bonus_packs - 1 WHERE id=?", (m.from_user.id,), commit=True)
        await m.answer("🎁 Bonus pack ochilmoqda...")
        await open_pack(bot, m.chat.id, m.from_user.id, "free")
        return
    if u["last_free"] == today():
        await m.answer("⏳ Bugungi bepul pack allaqachon ochilgan.\n"
                       f"Ertaga qaytib keling yoki «{BTN_SHOP}» ga kiring 😉")
        return
    q("UPDATE users SET last_free=? WHERE id=?", (today(), m.from_user.id), commit=True)
    await m.answer("🎴 Pack ochilmoqda...")
    await open_pack(bot, m.chat.id, m.from_user.id, "free")


@router.message(F.text == BTN_BONUS)
async def bonus_pack(m: Message, bot: Bot):
    register(m.from_user)
    u = q("SELECT bonus_packs FROM users WHERE id=?", (m.from_user.id,), one=True)
    if u["bonus_packs"] <= 0:
        await m.answer("🎁 Sizda bonus pack yo'q.")
        return
    q("UPDATE users SET bonus_packs = bonus_packs - 1 WHERE id=?", (m.from_user.id,), commit=True)
    await m.answer("🎁 Bonus pack ochilmoqda...")
    await open_pack(bot, m.chat.id, m.from_user.id, "free")


@router.message(F.text == BTN_MERGE)
async def merge_cards(m: Message):
    register(m.from_user)
    merged = merge_duplicate_cards(m.from_user.id)
    if not merged:
        await m.answer("🧩 3 ta bir xil kartaga ega bo'lmadingiz."
                       "\n3 ta bir xil kartani birlashtirish uchun «Mening kartalarim»da tekshiring.")
        return
    lines = [
        f"{RARITY[item['to']][0]} <b>{html.escape(item['card'])}</b> — {RARITY[item['to']][1]} pack kartasi"
        for item in merged
    ]
    await m.answer(f"🧩 Birlashtirish bajarildi!\n" + "\n".join(lines))


@router.message(F.text == BTN_TEAM)
async def team_info(m: Message):
    register(m.from_user)
    team_ids, score = build_team(m.from_user.id)
    if not team_ids:
        await m.answer("👥 Sizda jamoa uchun karta yo'q. Pack oching va kartalar to'plang.")
        return
    cards = [BY_ID[int(cid)] for cid in team_ids]
    txt = "👥 <b>Sizning jamoangiz</b>\n" + "\n".join(
        f"{RARITY[c['rarity']][0]} {html.escape(c['name'])} — ⭐{c['rating']} ({RARITY[c['rarity']][1]})"
        for c in cards)
    txt += f"\n\n💪 Jami kuch: <b>{score}</b>"
    prize = month_reward_if_needed(m.from_user.id)
    if prize:
        txt += f"\n🏆 <b>Bu oy g'olib siz bo'ldingiz! {prize} Stars berildi.</b>"
    await m.answer(txt)


@router.message(F.text == BTN_SHOP)
async def shop(m: Message):
    register(m.from_user)
    await m.answer("⭐ <b>Pack do'koni</b>\nQimmatroq pack — zo'r karta ehtimoli yuqoriroq!",
                   reply_markup=shop_kb())


@router.callback_query(F.data.startswith("buy:"))
async def buy_cb(c: CallbackQuery, bot: Bot):
    key = c.data.split(":")[1]
    p = PACKS.get(key)
    if not p or not p["price"]:
        await c.answer("Xato", show_alert=True)
        return
    await bot.send_invoice(
        chat_id=c.message.chat.id, title=f"{p['emoji']} {p['title']}",
        description=f"1 ta {p['title']} ochish", payload=f"pack:{key}",
        currency="XTR", provider_token="",
        prices=[LabeledPrice(label=p["title"], amount=p["price"])])
    await c.answer()


@router.pre_checkout_query()
async def pre_checkout(pcq: PreCheckoutQuery):
    await pcq.answer(ok=True)


@router.message(F.successful_payment)
async def paid_ok(m: Message, bot: Bot):
    register(m.from_user)
    key = (m.successful_payment.invoice_payload or "").split(":")[-1]
    if key not in PACKS or not PACKS[key]["price"]:
        key = "p30"
    await m.answer("✅ To'lov qabul qilindi! Pack ochilmoqda... 🎴")
    await open_pack(bot, m.chat.id, m.from_user.id, key)


@router.message(F.text == BTN_MY)
async def my_cards(m: Message):
    register(m.from_user)
    rows = q("SELECT card_id, cnt FROM cards WHERE user_id=?", (m.from_user.id,))
    have = {r["card_id"]: r["cnt"] for r in rows if r["card_id"] in BY_ID}
    if not have:
        await m.answer("🃏 Sizda hali karta yo'q. Pack oching! 🎴")
        return
    blocks = []
    for rar in ("legendary", "epic", "rare", "common"):
        emoji, label = RARITY[rar][:2]
        items = [f"  {emoji} {html.escape(c['name'])} (⭐{c['rating']}) ×{have[c['id']]}"
                 for c in BY_RARITY[rar] if c["id"] in have]
        if items:
            blocks.append(f"<b>{label}</b>\n" + "\n".join(items))
    epic_total = sum(have.get(c["id"], 0) for c in BY_RARITY["epic"])
    bonus = q("SELECT bonus_packs FROM users WHERE id=?", (m.from_user.id,), one=True)["bonus_packs"]
    blocks.append(f"🟣 Epik: <b>{epic_total % EPIC_SET_SIZE}/{EPIC_SET_SIZE}</b> (keyingi mukofotgacha)\n"
                  f"🃏 Jami: <b>{sum(have.values())}</b> ta karta\n"
                  f"🎁 Bonus packlar: <b>{bonus}</b>")
    await m.answer("\n\n".join(blocks))


@router.message(Command("invite"))
async def invite_cmd(m: Message):
    register(m.from_user)
    invite_url = f"https://t.me/{(m.bot.username or 'yourbot')}?start={m.from_user.id}"
    await m.answer(f"👥 Taklif havolasi:\n<code>{invite_url}</code>\n\n"
                   "Taklif qilgan odam qo'shilganda sizga <b>5 ta bonus pack</b> beriladi.")


@router.message(Command("merge"))
async def merge_cmd(m: Message):
    register(m.from_user)
    merged = merge_duplicate_cards(m.from_user.id)
    if not merged:
        await m.answer("🧩 Birlashtirish uchun 3 ta bir xil karta yetarli emas.")
        return
    lines = [
        f"{RARITY[item['to']][0]} <b>{html.escape(item['card'])}</b> — {RARITY[item['to']][1]} pack kartasi"
        for item in merged
    ]
    await m.answer("🧩 Birlashtirish bajarildi!\n" + "\n".join(lines))


@router.message(Command("team"))
async def team_cmd(m: Message):
    register(m.from_user)
    team_ids, score = build_team(m.from_user.id)
    if not team_ids:
        await m.answer("👥 Jamoa uchun karta yo'q.")
        return
    score_msg = "\n".join(
        f"{RARITY[BY_ID[int(cid)]['rarity']][0]} {html.escape(BY_ID[int(cid)]['name'])} — ⭐{BY_ID[int(cid)]['rating']}"
        for cid in team_ids)
    prize = month_reward_if_needed(m.from_user.id)
    txt = f"👥 <b>Jamoangiz</b>\n{score_msg}\n\n💪 Jami kuch: <b>{score}</b>"
    if prize:
        txt += f"\n🏆 <b>{prize} Stars mukofot olindi!</b>"
    await m.answer(txt)


@router.message(F.text == BTN_TOP)
async def top_users(m: Message):
    rows = q("SELECT id, name, packs FROM users WHERE packs > 0 ORDER BY packs DESC LIMIT 10")
    if not rows:
        await m.answer("🏆 Reyting hozircha bo'sh.")
        return
    medals = ["🥇", "🥈", "🥉"] + ["🔸"] * 7
    await m.answer("🏆 <b>Eng faol o'yinchilar</b>\n\n" + "\n".join(
        f"{medals[i]} {html.escape(r['name'] or '—')} — {r['packs']} pack" for i, r in enumerate(rows)))


# ---------------------------------------------------------------- admin
@router.message(F.text == BTN_A_USERS)
async def admin_users(m: Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer("👥 <b>Foydalanuvchilar bo'limi</b>\nTanlang:", reply_markup=admin_users_menu())


@router.message(F.text == BTN_A_BACK)
async def admin_back(m: Message):
    if not is_admin(m.from_user.id):
        return
    await m.answer("⬅️ Asosiy menyu", reply_markup=menu(m.from_user.id))


@router.message(F.text == BTN_A_PACK)
async def admin_pack(m: Message):
    if not is_admin(m.from_user.id):
        return
    rows = [[InlineKeyboardButton(text=f"{p['emoji']} {p['title']}", callback_data=f"adminpack:{k}")]
            for k, p in PACKS.items() if p["price"] >= 0]
    await m.answer("🎁 Qaysi pack berishni tanlang?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("adminpack:"))
async def admin_pack_cb(c: CallbackQuery, bot: Bot):
    if not is_admin(c.from_user.id):
        await c.answer("Faqat admin uchun", show_alert=True)
        return
    key = c.data.split(":", 1)[1]
    if key not in PACKS:
        await c.answer("Noto'g'ri pack", show_alert=True)
        return
    kb, ok = top_kb(pack_key=key)
    if not ok:
        await c.answer("Foydalanuvchi topilmadi", show_alert=True)
        return
    await c.message.answer(f"🎁 <b>{pack_label(key)}</b> packni kimga beramiz?", reply_markup=kb)
    await c.answer()


@router.message(Command("giftpack"))
async def gift_pack_cmd(m: Message, bot: Bot):
    if not is_admin(m.from_user.id):
        return
    parts = (m.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in PACKS:
        await m.answer("Foydalanish: /giftpack 123456789 p100")
        return
    uid = int(parts[1])
    key = parts[2]
    if not q("SELECT 1 FROM users WHERE id=?", (uid,), one=True):
        await m.answer("Bunday foydalanuvchi yo'q.")
        return
    q("UPDATE users SET gift=1, gift_pack_key=? WHERE id=?", (key, uid), commit=True)
    await notify_pack_gift(bot, uid, by_admin=True, pack_key=key)
    await m.answer(f"✅ {uid} ga <b>{pack_label(key)}</b> pack berildi.")


def top_kb(limit=10, pack_key=None):
    rows = q("SELECT id, name, packs, gift FROM users WHERE packs > 0 ORDER BY packs DESC LIMIT ?", (limit,))
    kb = [[InlineKeyboardButton(
        text=f"{'🎁' if r['gift'] else '👤'} {r['name']} — {r['packs']} pack",
        callback_data=f"gift:{r['id']}:{pack_key}" if pack_key else f"gift:{r['id']}")] for r in rows if r["id"] not in ADMIN_IDS]
    return InlineKeyboardMarkup(inline_keyboard=kb), bool(kb)


@router.message(F.text == BTN_A_GIFT)
async def admin_gift(m: Message):
    if not is_admin(m.from_user.id):
        return
    kb, ok = top_kb()
    if not ok:
        await m.answer("Hali faol foydalanuvchi yo'q.")
        return
    await m.answer("👑 Kimga zo'r karta sovg'a qilamiz?\n"
                   "Tanlangan odamning keyingi packidan afsonaviy karta chiqadi.\n"
                   "(🎁 — sovg'a allaqachon belgilangan)", reply_markup=kb)


@router.message(Command("clearcards"))
async def clear_cards_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return
    parts = (m.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await m.answer("Foydalanish: /clearcards 123456789")
        return
    uid = int(parts[1])
    q("DELETE FROM cards WHERE user_id=?", (uid,), commit=True)
    q("UPDATE users SET gift=0, gift_pack_key='free', team='', team_score=0 WHERE id=?", (uid,), commit=True)
    await m.answer(f"✅ {uid} foydalanuvchining barcha kartalari tozalandi.")
    try:
        await m.bot.send_message(uid, "🧹 Admin kartalaringizni tozaladi. Yana pack oching! 🎴")
    except Exception:
        pass


async def notify_pack_gift(bot: Bot, uid: int, *, by_admin: bool = True, pack_key: str = "free"):
    key = pack_key if pack_key in PACKS else "free"
    label = pack_label(key)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=f"🎴 {label}ni ochish",
        callback_data=f"open_gift_pack:{uid}:{key}")]])
    try:
        if by_admin:
            await bot.send_message(uid, f"🎁 <b>Admin sizga {label} pack berdi!</b>\nPackni ochish uchun tugmani bosing 👇",
                                  reply_markup=kb)
        else:
            await bot.send_message(uid, "🎉 <b>Faolligingiz uchun admin sizga sovg'a tayyorladi!</b>\n"
                                    "Keyingi packni oching 👀🎴")
    except Exception:
        pass


@router.callback_query(F.data.startswith("open_gift_pack:"))
async def open_gift_pack_cb(c: CallbackQuery, bot: Bot):
    parts = c.data.split(":")
    if len(parts) != 3:
        await c.answer("Xato", show_alert=True)
        return
    uid = int(parts[1])
    key = parts[2]
    if c.from_user.id != uid:
        await c.answer("Bu sizga tegishli emas", show_alert=True)
        return
    q("UPDATE users SET gift=0, gift_pack_key='free' WHERE id=?", (uid,), commit=True)
    await c.answer("🎴 Pack ochilmoqda...")
    await open_pack(bot, c.message.chat.id, uid, key if key in PACKS else "free", count_pack=False)
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("gift:"))
async def gift_cb(c: CallbackQuery, bot: Bot):
    if not is_admin(c.from_user.id):
        await c.answer("Faqat admin uchun", show_alert=True)
        return
    parts = c.data.split(":")
    uid = int(parts[1])
    key = parts[2] if len(parts) > 2 and parts[2] in PACKS else None
    q("UPDATE users SET gift=1, gift_pack_key=? WHERE id=?", (key or "free", uid), commit=True)
    if key:
        q("UPDATE users SET bonus_packs = bonus_packs + 1 WHERE id=?", (uid,), commit=True)
    u = q("SELECT name FROM users WHERE id=?", (uid,), one=True)
    await c.answer("✅ Belgilandi!")
    await c.message.edit_reply_markup(reply_markup=top_kb()[0])
    await notify_pack_gift(bot, uid, by_admin=True, pack_key=key or "free")
    pack_text = f" ({pack_label(key)})" if key else ""
    await c.message.answer(f"✅ {html.escape(u['name'])} uchun admin pack belgilandi{pack_text}.")


@router.message(Command("zor"))
async def zor_cmd(m: Message, bot: Bot):
    if not is_admin(m.from_user.id):
        return
    parts = (m.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await m.answer("Foydalanish: /zor 123456789")
        return
    uid = int(parts[1])
    if not q("SELECT 1 FROM users WHERE id=?", (uid,), one=True):
        await m.answer("Bunday foydalanuvchi botda yo'q.")
        return
    q("UPDATE users SET gift=1, gift_pack_key='free' WHERE id=?", (uid,), commit=True)
    await m.answer("✅ Belgilandi.")
    await notify_pack_gift(bot, uid, by_admin=True, pack_key="free")


@router.message(F.text == BTN_A_PRIZES)
async def admin_prizes(m: Message):
    if not is_admin(m.from_user.id):
        return
    rows = q("SELECT p.id, p.user_id, p.amount, p.reason, u.name FROM prizes p "
             "LEFT JOIN users u ON u.id = p.user_id WHERE p.done = 0")
    if not rows:
        await m.answer("💰 Berilmagan mukofot yo'q ✅")
        return
    for r in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Berildi", callback_data=f"done:{r['id']}")]])
        await m.answer(f"💰 {mention(r['user_id'], r['name'])} — <b>{r['amount']} Stars</b>\n"
                       f"Sabab: {r['reason']}", reply_markup=kb)


@router.callback_query(F.data.startswith("done:"))
async def prize_done(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("Faqat admin uchun", show_alert=True)
        return
    q("UPDATE prizes SET done=1 WHERE id=?", (int(c.data.split(":")[1]),), commit=True)
    await c.answer("✅ Belgilandi")
    await c.message.edit_text(c.message.html_text + "\n\n✅ <b>Berildi</b>")


@router.message(F.text == BTN_A_STATS)
async def admin_stats(m: Message):
    if not is_admin(m.from_user.id):
        return
    users = q("SELECT COUNT(*) AS n FROM users", one=True)["n"]
    packs = q("SELECT COALESCE(SUM(packs),0) AS n FROM users", one=True)["n"]
    cards = q("SELECT COALESCE(SUM(cnt),0) AS n FROM cards", one=True)["n"]
    pend = q("SELECT COUNT(*) AS n FROM prizes WHERE done=0", one=True)["n"]
    await m.answer(f"📊 <b>Statistika</b>\n\n👥 Foydalanuvchilar: <b>{users}</b>\n"
                   f"🎴 Ochilgan packlar: <b>{packs}</b>\n🃏 Berilgan kartalar: <b>{cards}</b>\n"
                   f"💰 Berilmagan mukofotlar: <b>{pend}</b>")


@router.message(F.text == BTN_A_ACTIVE)
async def admin_active(m: Message):
    if not is_admin(m.from_user.id):
        return
    rows = q("SELECT id, name, packs FROM users WHERE packs > 0 ORDER BY packs DESC LIMIT 20")
    if not rows:
        await m.answer("Hali faol foydalanuvchi yo'q.")
        return
    await m.answer("👥 <b>Eng faol 20 ta foydalanuvchi</b>\n\n" + "\n".join(
        f"{i + 1}. {mention(r['id'], r['name'])} — {r['packs']} pack (<code>{r['id']}</code>)"
        for i, r in enumerate(rows)))


# ---------------------------------------------------------------- ishga tushirish
async def main():
    logging.basicConfig(level=logging.INFO)
    if not BOT_TOKEN or not ADMIN_IDS:
        raise SystemExit("BOT_TOKEN va ADMIN_IDS ni o'rnating!")
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
