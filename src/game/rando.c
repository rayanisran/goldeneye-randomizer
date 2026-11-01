/*
 * GoldenEye randomizer runtime. See rando.h for the hook map.
 *
 * Seed file  ($S/rando/seed.bin, little-endian, written by randomizer/seedfile.py)
 *   0   "GERS"            4   u16 version      6  u8 difficulty   7 u8 options
 *   8   u32 seed lo       12  u32 seed hi      16 u32 start-level mask (SP_LEVEL bits)
 *   20  u8 aztec parent   21  u8 egypt parent  (SP level that unlocks it, 0xFF none)
 *   22  u16 item count    24  u16 loadout count 26 u16 top-up count
 *   28  u16 start pad[20]
 *   68  items, RANDO_ITEM_BYTES each:
 *       0 home  1 rectype  2 u16 homerec  4 s16 model  6 s8 weaponnum  7 kind
 *       8 place 9 mode     10 u16 ref     12 u32 flags 16 u32 flags2   20 name[40]
 *       60 u8 ammo type   61 reserved     62 u16 ammo amount (given on pickup)
 *   ..  loadout, 4 bytes each: u8 kind (0 weapon, 1 ammo), u8 id, u16 amount
 *   ..  top-ups, 6 bytes each: u8 level, u8 weapon, u8 ammo type, u8 reserved, u16 minimum
 *   ..  (optional) u16 n + new locks, 4 bytes each: u8 level, u8 key bit, u16 door record
 *   ..  (optional) u16 n + handovers, 4 bytes each: u8 level, u8 tag, u16 item index
 *       (the level's script gives Bond the object with that tag - Mishkin's safe
 *        key - so the item placed on that guard takes over the tag)
 *   modes: 0 pad, 1 guard, 2 inside a container, 3 inside a safe (ref = the
 *   safe-link record), 4 handed over when play starts (like Q's gadgets)
 *       (entering `level` while owning `weapon` raises that ammo to `minimum`, so a
 *        gadget used up elsewhere can't leave the level it belongs to unwinnable)
 *
 * Save ($S/rando/save-<seed>.bin): RandoSave below, written whole.
 */

#include <ultra64.h>
#include <string.h>
#include <bondconstants.h>
#include <bondtypes.h>
#include <memp.h>
#include "rando.h"
#include "bondinv.h"
#include "bondview.h"
#include "bondview_r.h"
#include "front.h"
#include "gun.h"
#include "loadobjectmodel.h"
#include "lv.h"
#include "player.h"
#include "propobj.h"
#include "chr.h"
#include "model.h"
#ifdef PORT
#include <stdlib.h>
#endif

#ifdef GE_RANDOMIZER

int bondinvHasInvItem(ITEM_IDS item);                      /* bondinv.c, not in bondinv.h */
bool bondinvHasDualWeapon(ITEM_IDS right, ITEM_IDS left);  /* bondinv.c, not in bondinv.h */
void add_ammo_to_inventory(AMMOTYPE ammotype, int amount, int doplaysound, int dodisplaytext); /* propobj.c */
s32 get_ammo_type_for_weapon(ITEM_IDS weapon);                                               /* gunfire.c */

/* Progress log: every run appends to $S/rando/log-<seed>.txt (level entries
 * and exits, pickups, deaths, unlocks) so a stuck run can be diagnosed from
 * the file alone. Hiding places are logged as item numbers only, never
 * described. GE_RANDOLOG=1 also echoes each line to the console. */
static void randoLog(const char *fmt, ...);
#define RANDOLOG randoLog

static const char *s_levelNames[] = {
    "Dam", "Facility", "Runway", "Surface 1", "Bunker 1", "Silo", "Frigate", "Surface 2",
    "Bunker 2", "Statue", "Archives", "Streets", "Depot", "Train", "Jungle", "Control",
    "Caverns", "Cradle", "Aztec", "Egyptian",
};
static const char *s_diffNames[] = { "Agent", "Secret Agent", "00 Agent", "007" };

#define RANDO_VERSION       1   /* seed file */
#define RANDO_SAVE_VERSION  2
#define RANDO_LEVELS        20
#define RANDO_MAX_ITEMS     128
#define RANDO_MAX_LOADOUT   32
#define RANDO_ITEM_BYTES    64
#define RANDO_NAME_LEN      40
#define RANDO_MAX_TOPUP     32
#define RANDO_MAX_RECORDS   1024
#define RANDO_AMMO_SLOTS    32
#define RANDO_ITEM_SLOTS    96

/* item kinds */
#define KIND_RECORD   0   /* key / objective prop: lives as a setup record */
#define KIND_INVENTORY 1  /* weapon or gadget ITEM_ID: carried in the weapon inventory */
#define KIND_CRADLEKEY 2  /* the GoldenEye Key that opens Cradle */
#define KIND_NEWKEY    3  /* key for a new lock: opens its level's locked door(s) */

#define RANDO_MAX_LOCKS 32
#define RANDO_MAX_TAGS  8
#define RANDO_MAX_SAFES 8

/* seed option bits */
#define OPT_BONUS_LEVELS   0x01
#define OPT_SHOW_HANDOVER  0x02   /* announce items handed over at level start */
#define OPT_GLOW_ITEMS     0x04   /* items still to find pulse gold, seen from afar */
#define OPT_CARRIER_GREYER 0x08   /* guards holding one are drawn slightly greyer */

/* placement modes */
#define MODE_PAD     0
#define MODE_GUARD   1
#define MODE_INSIDE  2
#define MODE_SAFE    3
#define MODE_START   4

#define NOLOAD_ALL   0x000000F0  /* PROPFLAG2 don't load on Agent/SA/00/007 */
#define PLACE_FLAGS  (PROPFLAG_ASSIGNEDTOCHR | PROPFLAG_INSIDEANOTHEROBJ | PROPFLAG_UNCOLLECTABLE | PROPFLAG_00080000)
/* how an object sits on its pad: fall to ground, upside-down / rotated, scale
 * to pad bounds, absolute position */
#define SAFE_POS_FLAGS (PROPFLAG_RENDERPOSTBG | PROPFLAG_ONSCREEN | PROPFLAG_ENABLED | PROPFLAG_00000010 \
                        | PROPFLAG_00000020 | PROPFLAG_00000040 | PROPFLAG_00000080 | PROPFLAG_00001000)

typedef struct RandoItem {
    u8   home;
    u8   rectype;
    u16  homerec;
    s16  model;
    s8   weaponnum;
    u8   kind;
    u8   place;
    u8   mode;
    u16  ref;
    u32  flags;
    u32  flags2;
    char name[RANDO_NAME_LEN];
    u8   ammotype;
    u8   keybit;   /* KIND_NEWKEY: door bit it opens on its home level */
    u16  ammo;
} RandoItem;

typedef struct RandoLock {
    u8  level;
    u8  bit;
    u16 door;      /* door record index in that level */
} RandoLock;

typedef struct RandoTag {
    u8  level;
    u8  tag;
    u16 item;
} RandoTag;

typedef struct RandoLoadout {
    u8  kind;
    u8  id;
    u16 amount;
} RandoLoadout;

typedef struct RandoTopup {
    u8  level;
    u8  weapon;
    u8  ammotype;
    u16 minimum;
} RandoTopup;

typedef struct RandoSave {
    char magic[4];
    u32  version;
    u32  seedlo, seedhi;
    u32  beaten;                      /* SP_LEVEL bits */
    u32  found[RANDO_MAX_ITEMS / 32];
    f32  health, armour;
    u32  weapons[RANDO_ITEM_SLOTS / 32];
    s32  ammo[RANDO_AMMO_SLOTS];
    u32  duals[RANDO_ITEM_SLOTS / 32];  /* dual-wield pairs owned (same gun both hands) */
    s8   equipped[2];                   /* right, left held at the end of the last level */
    u8   pad[2];
} RandoSave;

static struct {
    s32 tried, loaded;
    u8  difficulty, options;
    u32 seedlo, seedhi;
    u32 startmask;
    u8  bonusparent[2];
    u16 startpad[RANDO_LEVELS];
    s32 nitems, nloadout, ntopup, nlocks;
    RandoItem items[RANDO_MAX_ITEMS];
    RandoLoadout loadout[RANDO_MAX_LOADOUT];
    RandoTopup topup[RANDO_MAX_TOPUP];
    RandoLock locks[RANDO_MAX_LOCKS];
    s32 ntags;
    RandoTag tags[RANDO_MAX_TAGS];
} s_seed;

static RandoSave s_save;

/* live state for the level being played */
static s32 s_level = -1;              /* SP_LEVEL being played, -1 none */
static s32 s_completed;
static s32 s_died;
static u8 *s_propBase, *s_propEnd;    /* this level's setup records (vanilla + added) */
static u32 s_offsets[RANDO_MAX_RECORDS];  /* byte offset of each record from s_propBase */
static s32 s_nrec;
static struct { s32 link; s16 pad; } s_safes[RANDO_MAX_SAFES];   /* where each safe's contents sit */
static s32 s_nsafes;
static s32 s_playStarted;             /* intro over: handed-over items may be collected */

s32 g_randoHighlightMsg;
s32 g_randoSilentPickup;
static s32 s_snapValid;
static u32 s_snapWeapons[RANDO_ITEM_SLOTS / 32];
static u32 s_snapDuals[RANDO_ITEM_SLOTS / 32];
static s8  s_snapEquipped[2];
static s32 s_snapAmmo[RANDO_AMMO_SLOTS];
static f32 s_snapHealth, s_snapArmour;
static s32 s_tickCount;

static struct {
    ObjectRecord *rec;
    s16 item;
    s16 appended;   /* record added by the randomizer (not the level's own) */
    s16 carried;    /* already found: handed over silently when play starts */
    s16 atstart;    /* MODE_START: handed over when play starts, like Q's gadgets */
    s32 recindex;   /* its record number in this level */
} s_tracked[RANDO_MAX_ITEMS];
static s32 s_ntracked;
static char s_invNames[RANDO_MAX_ITEMS][RANDO_NAME_LEN];   /* watch names of added records */

static s32 randoIoLoadSeed(u8 *buf, s32 max);
static s32 randoIoLoadSave(RandoSave *save);
static void randoIoWriteSave(const RandoSave *save);

/* ------------------------------------------------------------ helpers */

static u16 rd16(const u8 *p) { return (u16)(p[0] | (p[1] << 8)); }
static u32 rd32(const u8 *p) { return (u32)p[0] | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24); }

static s32 bitGet(const u32 *bits, s32 i) { return (bits[i >> 5] >> (i & 31)) & 1; }
static void bitSet(u32 *bits, s32 i) { bits[i >> 5] |= 1u << (i & 31); }

static s32 itemFound(s32 i) { return bitGet(s_save.found, i); }

/* Ammo types that carry between levels: ordinary ammo (9mm..golden bullets)
 * AND gadget charges past AMMOTYPE_GLOBAL_MAX: laser/magnet watch energy,
 * camera film, bugs, plastique. Only the GoldenEye-key, tank and token
 * pseudo-ammo stay out. (Gadget ammo used to reset to 0 on every level:
 * laser watch empty on Aztec, 10-30 playtest.) */
static s32 carriedAmmo(s32 type)
{
    return type >= 1 && type < AMMOTYPE_MAX && type < RANDO_AMMO_SLOTS
        && type != AMMO_GEKEY && type != AMMO_TANK && type != AMMO_TOKEN;
}

static void appendNum(char *buf, s32 n)
{
    char tmp[12];
    s32 len = 0;

    if (n < 0)
    {
        strcat(buf, "-");
        n = -n;
    }
    do
    {
        tmp[len++] = '0' + n % 10;
        n /= 10;
    } while (n > 0 && len < 11);
    buf += strlen(buf);
    while (len > 0)
    {
        *buf++ = tmp[--len];
    }
    *buf = '\0';
}

/* "weapons 4 8 38 | ammo 1:21 5:10 | holding 8/0 | health 0.75 armour 0.00" */
static void logInventory(const char *what)
{
    char inv[384] = "";
    s32 i;

    strcat(inv, "weapons");
    for (i = ITEM_KNIFE; i < RANDO_ITEM_SLOTS; i++)
    {
        if (bitGet(s_save.weapons, i))
        {
            strcat(inv, " ");
            appendNum(inv, i);
            if (bitGet(s_save.duals, i))
            {
                strcat(inv, "x2");
            }
        }
    }
    strcat(inv, " | ammo");
    for (i = 1; i < RANDO_AMMO_SLOTS; i++)
    {
        if (s_save.ammo[i] != 0)
        {
            strcat(inv, " ");
            appendNum(inv, i);
            strcat(inv, ":");
            appendNum(inv, s_save.ammo[i]);
        }
    }
    strcat(inv, " | holding ");
    appendNum(inv, s_save.equipped[0]);
    strcat(inv, "/");
    appendNum(inv, s_save.equipped[1]);
    RANDOLOG("    %s: %s | health %.2f armour %.2f\n", what, inv, s_save.health, s_save.armour);
}

static s32 levelEnabled(s32 lvl)
{
    if (lvl == SP_LEVEL_AZTEC || lvl == SP_LEVEL_EGYPT)
    {
        return (s_seed.options & OPT_BONUS_LEVELS) != 0;
    }
    return lvl >= SP_LEVEL_DAM && lvl < SP_LEVEL_AZTEC;
}

static s32 hasCradleKey(void)
{
    s32 i;

    for (i = 0; i < s_seed.nitems; i++)
    {
        if (s_seed.items[i].kind == KIND_CRADLEKEY && itemFound(i))
        {
            return TRUE;
        }
    }
    return FALSE;
}

static s32 cradleUnlocked(void)
{
    s32 lvl;

    for (lvl = 0; lvl < RANDO_LEVELS; lvl++)
    {
        if (lvl != SP_LEVEL_CRADLE && levelEnabled(lvl) && !bitGet(&s_save.beaten, lvl))
        {
            return FALSE;
        }
    }
    return hasCradleKey();
}

static s32 levelUnlocked(s32 lvl)
{
    if (!levelEnabled(lvl))
    {
        return FALSE;
    }
    if (lvl == SP_LEVEL_CRADLE)
    {
        return cradleUnlocked();
    }
    if (s_seed.startmask & (1u << lvl))
    {
        return TRUE;
    }
    if (lvl == SP_LEVEL_AZTEC || lvl == SP_LEVEL_EGYPT)
    {
        u8 parent = s_seed.bonusparent[lvl - SP_LEVEL_AZTEC];
        return parent < RANDO_LEVELS && bitGet(&s_save.beaten, parent);
    }
    return lvl > SP_LEVEL_DAM && bitGet(&s_save.beaten, lvl - 1);
}

static s32 currentSoloLevel(void)
{
    if (briefingpage < 0 || getPlayerCount() != 1)
    {
        return -1;
    }
    return mission_folder_setup_entries[briefingpage].mission_num;
}

/* ------------------------------------------------------------ load */

static void randoLoad(void)
{
    static u8 buf[68 + RANDO_MAX_ITEMS * RANDO_ITEM_BYTES + RANDO_MAX_LOADOUT * 4 + RANDO_MAX_TOPUP * 6
                  + 2 + RANDO_MAX_LOCKS * 4 + 2 + RANDO_MAX_TAGS * 4];
    s32 len, i, off;

    s_seed.tried = TRUE;
    len = randoIoLoadSeed(buf, sizeof(buf));

    if (len < 68 || memcmp(buf, "GERS", 4) != 0 || rd16(buf + 4) != RANDO_VERSION)
    {
        return;
    }

    s_seed.difficulty = buf[6];
    s_seed.options = buf[7];
    s_seed.seedlo = rd32(buf + 8);
    s_seed.seedhi = rd32(buf + 12);
    s_seed.startmask = rd32(buf + 16);
    s_seed.bonusparent[0] = buf[20];
    s_seed.bonusparent[1] = buf[21];
    s_seed.nitems = rd16(buf + 22);
    s_seed.nloadout = rd16(buf + 24);
    s_seed.ntopup = rd16(buf + 26);

    if (s_seed.nitems > RANDO_MAX_ITEMS || s_seed.nloadout > RANDO_MAX_LOADOUT || s_seed.ntopup > RANDO_MAX_TOPUP
        || len < 68 + s_seed.nitems * RANDO_ITEM_BYTES + s_seed.nloadout * 4 + s_seed.ntopup * 6)
    {
        return;
    }

    for (i = 0; i < RANDO_LEVELS; i++)
    {
        s_seed.startpad[i] = rd16(buf + 28 + i * 2);
    }

    off = 68;
    for (i = 0; i < s_seed.nitems; i++, off += RANDO_ITEM_BYTES)
    {
        RandoItem *it = &s_seed.items[i];
        const u8 *p = buf + off;

        it->home = p[0];
        it->rectype = p[1];
        it->homerec = rd16(p + 2);
        it->model = (s16)rd16(p + 4);
        it->weaponnum = (s8)p[6];
        it->kind = p[7];
        it->place = p[8];
        it->mode = p[9];
        it->ref = rd16(p + 10);
        it->flags = rd32(p + 12);
        it->flags2 = rd32(p + 16);
        memcpy(it->name, p + 20, RANDO_NAME_LEN);
        it->name[RANDO_NAME_LEN - 1] = '\0';
        it->ammotype = p[60];
        it->keybit = p[61];
        it->ammo = rd16(p + 62);
    }

    for (i = 0; i < s_seed.nloadout; i++, off += 4)
    {
        s_seed.loadout[i].kind = buf[off];
        s_seed.loadout[i].id = buf[off + 1];
        s_seed.loadout[i].amount = rd16(buf + off + 2);
    }

    for (i = 0; i < s_seed.ntopup; i++, off += 6)
    {
        s_seed.topup[i].level = buf[off];
        s_seed.topup[i].weapon = buf[off + 1];
        s_seed.topup[i].ammotype = buf[off + 2];
        s_seed.topup[i].minimum = rd16(buf + off + 4);
    }

    /* new locks (optional section: older seed files end before it) */
    s_seed.nlocks = 0;
    if (off + 2 <= len)
    {
        s32 n = rd16(buf + off);

        off += 2;
        for (i = 0; i < n && i < RANDO_MAX_LOCKS && off + 4 <= len; i++, off += 4)
        {
            s_seed.locks[i].level = buf[off];
            s_seed.locks[i].bit = buf[off + 1];
            s_seed.locks[i].door = rd16(buf + off + 2);
            s_seed.nlocks++;
        }
        off += (n - i) * 4;   /* skip any beyond the table */
    }

    /* scripted handovers (optional section) */
    s_seed.ntags = 0;
    if (off + 2 <= len)
    {
        s32 n = rd16(buf + off);

        off += 2;
        for (i = 0; i < n && i < RANDO_MAX_TAGS && off + 4 <= len; i++, off += 4)
        {
            s_seed.tags[i].level = buf[off];
            s_seed.tags[i].tag = buf[off + 1];
            s_seed.tags[i].item = rd16(buf + off + 2);
            s_seed.ntags++;
        }
    }

    if (!randoIoLoadSave(&s_save) || memcmp(s_save.magic, "GERV", 4) != 0
        || s_save.version != RANDO_SAVE_VERSION
        || s_save.seedlo != s_seed.seedlo || s_save.seedhi != s_seed.seedhi)
    {
        /* new run: starting loadout from the seed, full health, no armour */
        memset(&s_save, 0, sizeof(s_save));
        memcpy(s_save.magic, "GERV", 4);
        s_save.version = RANDO_SAVE_VERSION;
        s_save.seedlo = s_seed.seedlo;
        s_save.seedhi = s_seed.seedhi;
        s_save.health = 1.0f;
        s_save.equipped[0] = ITEM_NOTHING;
        s_save.equipped[1] = ITEM_NOTHING;

        for (i = 0; i < s_seed.nloadout; i++)
        {
            RandoLoadout *l = &s_seed.loadout[i];

            if (l->kind == 0 && l->id < RANDO_ITEM_SLOTS)
            {
                bitSet(s_save.weapons, l->id);
            }
            else if (l->kind == 1 && l->id < RANDO_AMMO_SLOTS)
            {
                s_save.ammo[l->id] += l->amount;
            }
        }

        randoIoWriteSave(&s_save);
    }

    s_seed.loaded = TRUE;
    {
        char open[256] = "", done[256] = "";
        s32 nfound = 0;

        for (i = 0; i < RANDO_LEVELS; i++)
        {
            if (bitGet(&s_save.beaten, i))
            {
                strcat(done, s_levelNames[i]);
                strcat(done, ", ");
            }
            else if (levelUnlocked(i))
            {
                strcat(open, s_levelNames[i]);
                strcat(open, ", ");
            }
        }
        for (i = 0; i < s_seed.nitems; i++)
        {
            nfound += itemFound(i);
        }
        RANDOLOG("=== seed %08x%08x loaded (%s, %d items). Items found %d/%d. Beaten: %s Unlocked: %s\n",
                 s_seed.seedhi, s_seed.seedlo, s_diffNames[s_seed.difficulty & 3], s_seed.nitems,
                 nfound, s_seed.nitems, done[0] ? done : "none. ", open[0] ? open : "none");
    }
}

s32 randoActive(void)
{
    if (!s_seed.tried)
    {
        randoLoad();
    }
    return s_seed.loaded;
}

/* ------------------------------------------------------------ level load */

static s32 recordBytes(s32 type)
{
    PropDefHeaderRecord hdr;

    memset(&hdr, 0, sizeof(hdr));
    hdr.type = type;
    return sizepropdef(&hdr) * 4;
}

/* MODE_SAFE: the item sits where the safe's own contents were, and the safe's
 * link record points at it instead, so it stays locked in until the safe is
 * opened. Returns the pad. */
static s32 safeLink(s32 link, s32 recindex)
{
    s32 i;

    for (i = 0; i < s_nsafes; i++)
    {
        if (s_safes[i].link == link)
        {
            ((struct SafeObjectRecord *)(s_propBase + s_offsets[link]))->Index1 = recindex - link;
            RANDOLOG("    safe (link %d) now holds record %d\n", link, recindex);
            return s_safes[i].pad;
        }
    }
    return 0;
}

static void placeRecord(ObjectRecord *rec, const RandoItem *it, s32 recindex)
{
    rec->flags &= ~PLACE_FLAGS;
    rec->flags2 &= ~NOLOAD_ALL;
    if (rec->type == PROPDEF_PROP)
    {
        /* Objective props need the "can be picked up" flag to be collected by
         * walking over them. Statue's flight recorder has none (a Statue script
         * hands it over), so away from Statue it could not be picked up. */
        rec->flags |= PROPFLAG_00040000;
    }

    switch (it->mode)
    {
        case MODE_GUARD:
            rec->flags |= PROPFLAG_ASSIGNEDTOCHR;
            rec->pad = it->ref;
            break;
        case MODE_INSIDE:
            rec->flags |= PROPFLAG_INSIDEANOTHEROBJ;
            rec->pad = (s16)(it->ref - recindex);
            break;
        case MODE_SAFE:
            /* held in place at the pad like every vanilla safe's contents ("in
             * air"); an item's own "fall to ground" dropped it onto the top of
             * the safe instead (Depot safe key, 10-31) */
            rec->flags &= ~SAFE_POS_FLAGS;
            rec->flags |= PROPFLAG_00000008;
            rec->pad = safeLink(it->ref, recindex);
            break;
        case MODE_START:
            rec->pad = s_seed.startpad[s_level];
            break;
        default:
            rec->pad = it->ref;
            break;
    }
}

static void buildRecord(ObjectRecord *rec, const RandoItem *it, s32 recindex, s32 bytes)
{
    u32 damagebits = 1000u << 16; /* what every vanilla collectable carries in this slot */

    memset(rec, 0, bytes);
    rec->extrascale = 256;
    rec->type = it->rectype;
    rec->obj = it->model;
    rec->flags = it->flags;
    rec->flags2 = it->flags2;
    memcpy(&rec->damage, &damagebits, sizeof(damagebits));

    if (it->rectype == PROPDEF_COLLECTABLE)
    {
        WeaponObjRecord *w = (WeaponObjRecord *)rec;

        w->weaponnum = it->weaponnum;
        w->LinkedWeaponType = -1;
        w->timer = -1;
    }
    else if (it->rectype == PROPDEF_KEY)
    {
        /* a key away from home opens nothing; a new-lock key opens its level's door */
        ((KeyRecord *)rec)->keyflags = (it->kind == KIND_NEWKEY && it->home == s_level) ? it->keybit : 0;
    }

    placeRecord(rec, it, recindex);
}

static void track(ObjectRecord *rec, s32 item, s32 appended, s32 carried, s32 recindex)
{
    if (s_ntracked < RANDO_MAX_ITEMS)
    {
        s_tracked[s_ntracked].rec = rec;
        s_tracked[s_ntracked].item = item;
        s_tracked[s_ntracked].appended = appended;
        s_tracked[s_ntracked].carried = carried;
        s_tracked[s_ntracked].atstart = !carried && s_seed.items[item].mode == MODE_START;
        s_tracked[s_ntracked].recindex = recindex;
        s_ntracked++;
    }
}

/* Does this level get an added record for item i? *carried = it is a copy of
 * something already found, handed over at the start so everything collected
 * shows in the inventory on every level (keys from elsewhere open nothing). */
static s32 appendWanted(const RandoItem *it, s32 i, s32 lvl, s32 *carried)
{
    *carried = FALSE;
    if (!itemFound(i))
    {
        return it->place == lvl && !(it->kind == KIND_RECORD && it->home == lvl);
    }
    if (it->rectype == PROPDEF_COLLECTABLE)
    {
        /* a found weapon (the Golden Gun) is already carried in by the weapon
         * inventory; force-picking up a copy freed its prop under the handover
         * and crashed on entering the next level (10-31) */
        return FALSE;
    }
    if ((it->kind == KIND_RECORD && it->home != lvl)
        || it->kind == KIND_NEWKEY                                    /* no vanilla record: always a copy */
        || (it->kind == KIND_CRADLEKEY && lvl != SP_LEVEL_BUNKER1))   /* Bunker 1 checks for a GoldenEye Key */
    {
        *carried = TRUE;
        return TRUE;
    }
    return FALSE;
}

/* Short watch-inventory name from the pickup text: "Picked up the clearance
 * A keycard." -> "Clearance A keycard\n". Game text ends every entry with a
 * newline and the watch list stops drawing there; without it the next name
 * in memory ran onto the same line (10-30 playtest). */
static void shortName(char *out, const char *pickup)
{
    const char *s = pickup;
    s32 n;

    if (strncmp(s, "Picked up ", 10) == 0) s += 10;
    if (strncmp(s, "the ", 4) == 0) s += 4;
    else if (strncmp(s, "a ", 2) == 0) s += 2;
    else if (strncmp(s, "an ", 3) == 0) s += 3;
    strncpy(out, s, RANDO_NAME_LEN - 2);
    out[RANDO_NAME_LEN - 2] = '\0';
    n = strlen(out);
    if (n > 0 && out[n - 1] == '.') out[--n] = '\0';
    if (out[0] >= 'a' && out[0] <= 'z') out[0] -= 'a' - 'A';
    out[n] = '\n';
    out[n + 1] = '\0';
}

void randoPatchSetup(s32 stageId)
{
    u32 *offsets = s_offsets;
    PropDefHeaderRecord *p;
    u8 *base, *newbase;
    s32 nrec, used, endbytes, extra, lvl, i, appendidx;

    s_ntracked = 0;
    s_level = -1;
    s_completed = FALSE;
    s_snapValid = FALSE;
    s_tickCount = 0;
    s_propBase = s_propEnd = NULL;
    s_playStarted = FALSE;

    lvl = currentSoloLevel();
    if (!randoActive() || lvl < 0 || g_CurrentSetup.propDefs == NULL)
    {
        return;
    }
    s_level = lvl;

    base = (u8 *)g_CurrentSetup.propDefs;
    nrec = 0;
    for (p = (PropDefHeaderRecord *)base; p->type != PROPDEF_END; p = (PropDefHeaderRecord *)((u32 *)p + sizepropdef(p)))
    {
        if (nrec < RANDO_MAX_RECORDS)
        {
            offsets[nrec] = (u8 *)p - base;
        }
        nrec++;
    }
    used = (u8 *)p - base;
    endbytes = sizepropdef(p) * 4;

    if (nrec > RANDO_MAX_RECORDS)
    {
        return;
    }

    /* items the randomizer adds to this level: placed here, not found yet,
     * and not simply a vanilla record of this level being moved */
    extra = 0;
    for (i = 0; i < s_seed.nitems; i++)
    {
        s32 carried;

        if (appendWanted(&s_seed.items[i], i, lvl, &carried))
        {
            extra += recordBytes(s_seed.items[i].rectype);
        }
    }

    newbase = base;
    if (extra > 0)
    {
        newbase = mempAllocBytesInBank(used + extra + endbytes, MEMPOOL_STAGE);
        memcpy(newbase, base, used);
        memcpy(newbase + used + extra, base + used, endbytes);
        g_CurrentSetup.propDefs = (void *)newbase;
    }
    s_propBase = newbase;
    s_propEnd = newbase + used + extra + endbytes;
    s_nrec = nrec;

    /* where each safe's contents sit, read before any record moves */
    s_nsafes = 0;
    for (i = 0; i < nrec && s_nsafes < RANDO_MAX_SAFES; i++)
    {
        struct SafeObjectRecord *link = (struct SafeObjectRecord *)(newbase + offsets[i]);

        if (link->type == PROPDEF_SAFE_ITEM && i + link->Index1 >= 0 && i + link->Index1 < nrec)
        {
            s_safes[s_nsafes].link = i;
            s_safes[s_nsafes].pad = ((ObjectRecord *)(newbase + offsets[i + link->Index1]))->pad;
            s_nsafes++;
        }
    }

    /* new locks: normally-open doors that now need this level's new key */
    for (i = 0; i < s_seed.nlocks; i++)
    {
        RandoLock *lk = &s_seed.locks[i];

        if (lk->level == lvl && lk->door < nrec)
        {
            DoorRecord *door = (DoorRecord *)(newbase + offsets[lk->door]);

            if (door->type == PROPDEF_DOOR)
            {
                door->keyflags |= lk->bit;
                RANDOLOG("    new lock: record %d now needs key bit %d\n", lk->door, lk->bit);
            }
        }
    }

    /* vanilla records of shuffled items that belong to this level */
    for (i = 0; i < s_seed.nitems; i++)
    {
        RandoItem *it = &s_seed.items[i];
        ObjectRecord *rec;

        if (it->home != lvl || it->homerec >= nrec)
        {
            continue;
        }
        rec = (ObjectRecord *)(newbase + offsets[it->homerec]);

        if (it->kind == KIND_RECORD && itemFound(i))
        {
            /* carried in from another level: hand it over at the start pad */
            RandoItem given = *it;
            given.mode = MODE_PAD;
            given.ref = s_seed.startpad[lvl];
            placeRecord(rec, &given, it->homerec);
            track(rec, i, FALSE, TRUE, it->homerec);
        }
        else if (it->kind == KIND_RECORD && it->place == lvl)
        {
            placeRecord(rec, it, it->homerec);
            track(rec, i, FALSE, FALSE, it->homerec);
        }
        else
        {
            rec->flags2 |= NOLOAD_ALL;
        }
    }

    /* items from elsewhere (or inventory items) hidden in this level */
    appendidx = nrec;
    for (i = 0; i < s_seed.nitems; i++)
    {
        RandoItem copy = s_seed.items[i];
        s32 bytes, carried;

        if (!appendWanted(&copy, i, lvl, &carried))
        {
            continue;
        }
        if (carried)
        {
            copy.mode = MODE_PAD;
            copy.ref = s_seed.startpad[lvl];
        }
        bytes = recordBytes(copy.rectype);
        buildRecord((ObjectRecord *)(newbase + used), &copy, appendidx, bytes);
        if (s_ntracked < RANDO_MAX_ITEMS)
        {
            shortName(s_invNames[s_ntracked], copy.name);
        }
        track((ObjectRecord *)(newbase + used), i, TRUE, carried, appendidx);
        used += bytes;
        appendidx++;
    }

    /* scripted handovers: the item now on that guard takes over the tag */
    for (i = 0; i < s_seed.ntags; i++)
    {
        RandoTag *tg = &s_seed.tags[i];
        s32 k, r;

        if (tg->level != lvl)
        {
            continue;
        }
        for (k = 0; k < s_ntracked; k++)
        {
            if (s_tracked[k].item == tg->item && !s_tracked[k].carried)
            {
                break;
            }
        }
        if (k == s_ntracked)
        {
            continue;   /* found already: it comes in with Bond, nothing to hand over */
        }
        for (r = 0; r < nrec; r++)
        {
            TagObjectRecord *tag = (TagObjectRecord *)(newbase + offsets[r]);

            if (tag->type == PROPDEF_TAG && tag->ID == tg->tag)
            {
                tag->OffsetToObj = (s16)(s_tracked[k].recindex - r);
                RANDOLOG("    handover: tag %d now gives item #%d\n", tg->tag, tg->item);
            }
        }
    }

    {
        char handed[192] = "", hidden[192] = "";

        for (i = 0; i < s_ntracked; i++)
        {
            s32 item = s_tracked[i].item;
            char *buf = itemFound(item) ? handed : hidden;

            strcat(buf, "#");
            appendNum(buf, item);
            strcat(buf, " ");
        }
        RANDOLOG("--> Enter %s (%s). Items hidden here: %s. Carried in and handed over: %s. [%d records, %d bytes added]\n",
                 s_levelNames[lvl], s_diffNames[lvlGetSelectedDifficulty() & 3], hidden[0] ? hidden : "none",
                 handed[0] ? handed : "none", nrec, extra);
    }
}

/* ------------------------------------------------------------ loadout */

s32 randoSkipVanillaLoadout(void)
{
    return randoActive() && s_level >= 0;
}

static const s8 s_preferredStart[] = {
    ITEM_WPPKSIL, ITEM_WPPK, ITEM_MP5KSIL, ITEM_MP5K, ITEM_TT33, ITEM_SKORPION, ITEM_UZI,
    ITEM_SPECTRE, ITEM_FNP90, ITEM_AK47, ITEM_M16, ITEM_SHOTGUN, ITEM_AUTOSHOT, ITEM_RUGER,
    ITEM_SNIPERRIFLE, ITEM_SILVERWPPK, ITEM_GOLDWPPK, ITEM_LASER, ITEM_GOLDENGUN, ITEM_KNIFE,
};

static s32 owned(s32 item)
{
    return item == ITEM_UNARMED || item == ITEM_FIST
        || (item > ITEM_FIST && item < RANDO_ITEM_SLOTS && bitGet(s_save.weapons, item));
}

void randoApplyLoadout(s32 *startright, s32 *startleft, s32 *setstarting)
{
    s32 i;
    s32 right = s_save.equipped[0];
    s32 left = s_save.equipped[1];

    if (!randoSkipVanillaLoadout())
    {
        return;
    }

    for (i = ITEM_KNIFE; i < RANDO_ITEM_SLOTS && i < ITEM_IDS_MAX; i++)
    {
        if (bitGet(s_save.weapons, i))
        {
            weaponLoadProjectileModels(i);
            bondinvAddInvItem(i);
        }
        if (bitGet(s_save.duals, i))
        {
            bondinvAddDoublesInvItem(i, i);
        }
    }
    if (bitGet(s_save.weapons, ITEM_REMOTEMINE))
    {
        bondinvAddInvItem(ITEM_TRIGGER);
    }

    for (i = 1; i < RANDO_AMMO_SLOTS; i++)
    {
        if (carriedAmmo(i) && s_save.ammo[i] > 0)
        {
            give_cur_player_ammo(i, s_save.ammo[i]);
        }
    }

    /* Q-Branch resupply: gadgets this level needs come back to their
     * original count, however many were spent elsewhere. */
    for (i = 0; i < s_seed.ntopup; i++)
    {
        RandoTopup *t = &s_seed.topup[i];

        if (t->level == s_level && owned(t->weapon))
        {
            s32 have = currentPlayerGetAmmoCount(t->ammotype);

            if (have < t->minimum)
            {
                /* give_cur_player_ammo SETS the count (clamped to the max) */
                give_cur_player_ammo(t->ammotype, t->minimum);
            }
        }
    }

    if (right != ITEM_NOTHING && owned(right))
    {
        /* whatever was in hand when the last level ended */
        *startright = right;
        *setstarting = 1;
        if (left != ITEM_NOTHING && left == right && bitGet(s_save.duals, right))
        {
            *startleft = left;
        }
    }
    else
    {
        /* first level of the run: best starting gun owned */
        for (i = 0; i < (s32)(sizeof(s_preferredStart) / sizeof(s_preferredStart[0])); i++)
        {
            if (bitGet(s_save.weapons, s_preferredStart[i]))
            {
                *startright = s_preferredStart[i];
                *setstarting = 1;
                break;
            }
        }
    }

    RANDOLOG("    spawn holding %d/%d\n", *startright, *startleft);
    logInventory("carried in");
    g_CurrentPlayer->bondhealth = s_save.health;
    g_CurrentPlayer->oldhealth = s_save.health;
    g_CurrentPlayer->apparenthealth = s_save.health;
    g_CurrentPlayer->bondarmour = s_save.armour;
    g_CurrentPlayer->oldarmour = s_save.armour;
    g_CurrentPlayer->apparentarmour = s_save.armour;
}

/* ------------------------------------------------------------ pickups */

char *randoInvName(ObjectRecord *obj)
{
    s32 i;

    for (i = 0; i < s_ntracked; i++)
    {
        if (s_tracked[i].rec == obj && s_tracked[i].appended && s_invNames[i][0])
        {
            return s_invNames[i];
        }
    }
    return NULL;
}

int randoMenuItemNames(const char **names, int max)
{
    /* Menu item list (port optionsoverlay.c): short names of every item found
     * so far, alphabetical, no levels. -1 when not on the menus of a seed. */
    static char buf[RANDO_MAX_ITEMS][RANDO_NAME_LEN];
    s32 i, j, n = 0;

    if (!randoActive() || s_level >= 0)
    {
        return -1;
    }
    for (i = 0; i < s_seed.nitems && n < max; i++)
    {
        if (!itemFound(i))
        {
            continue;
        }
        shortName(buf[n], s_seed.items[i].name);
        buf[n][strcspn(buf[n], "\n")] = '\0';
        names[n] = buf[n];
        n++;
    }
    for (i = 1; i < n; i++)   /* insertion sort, alphabetical */
    {
        for (j = i; j > 0 && strcmp(names[j - 1], names[j]) > 0; j--)
        {
            const char *tmp = names[j];
            names[j] = names[j - 1];
            names[j - 1] = tmp;
        }
    }
    return n;
}

void randoLogEvent(const char *line)
{
    if (s_seed.loaded)
    {
        RANDOLOG("%s", line);
    }
}

s32 randoExtraInvSlots(void)
{
    /* room for everything the run can carry, on top of the level's own 30 */
    return randoActive() && s_level >= 0 ? RANDO_MAX_ITEMS : 0;
}

s32 randoBlockPickup(ObjectRecord *obj)
{
    s32 i;

    if (s_level < 0 || s_playStarted)
    {
        return FALSE;
    }
    for (i = 0; i < s_ntracked; i++)
    {
        if (s_tracked[i].rec == obj && (s_tracked[i].carried || s_tracked[i].atstart))
        {
            return TRUE;   /* handed over on the first frame of play instead */
        }
    }
    return FALSE;
}

char *randoOnPickup(ObjectRecord *obj)
{
    s32 i;

    g_randoSilentPickup = FALSE;
    if (s_level < 0)
    {
        return NULL;
    }

    for (i = 0; i < s_ntracked; i++)
    {
        if (s_tracked[i].rec == obj)
        {
            RandoItem *it = &s_seed.items[s_tracked[i].item];

            if (s_tracked[i].carried)
            {
                /* handing over what you already carry: silent unless the seed
                 * asks for it (announcing it would hint which level needs it) */
                s32 show = (s_seed.options & OPT_SHOW_HANDOVER) != 0;

                RANDOLOG("    handed over #%d (camera mode %d)\n", s_tracked[i].item, g_CameraMode);
                g_randoHighlightMsg = show;
                g_randoSilentPickup = !show;   /* every carried key beeping at once was one loud beep */
                return show && s_tracked[i].appended && it->name[0] ? it->name : NULL;
            }

            g_randoHighlightMsg = TRUE;   /* this pickup's message is drawn in yellow */

            if (!itemFound(s_tracked[i].item))
            {
                bitSet(s_save.found, s_tracked[i].item);
                if (it->kind == KIND_INVENTORY && it->weaponnum > 0 && it->weaponnum < RANDO_ITEM_SLOTS)
                {
                    bitSet(s_save.weapons, it->weaponnum);
                    if (it->weaponnum == ITEM_REMOTEMINE)
                    {
                        bondinvAddInvItem(ITEM_TRIGGER);
                    }
                }
                if (it->ammotype != 0 && it->ammo != 0)
                {
                    /* add to what's held (give_cur_player_ammo would replace it) */
                    add_ammo_to_inventory(it->ammotype, it->ammo, FALSE, FALSE);
                }
                randoIoWriteSave(&s_save);
                RANDOLOG("    FOUND item #%d on %s: %s\n", s_tracked[i].item, s_levelNames[s_level], it->name);
                if (it->kind == KIND_CRADLEKEY)
                {
                    RANDOLOG("    (Cradle key in hand; Cradle %s)\n",
                             cradleUnlocked() ? "is now UNLOCKED" : "still needs every other level beaten");
                }
            }
            return s_tracked[i].appended && it->name[0] ? it->name : NULL;
        }
    }
    return NULL;
}

/* ------------------------------------------------------------ progress */

static void snapshot(void)
{
    s32 i;

    if (g_CurrentPlayer == NULL)
    {
        return;
    }

    memset(s_snapWeapons, 0, sizeof(s_snapWeapons));
    memset(s_snapDuals, 0, sizeof(s_snapDuals));
    for (i = ITEM_KNIFE; i < RANDO_ITEM_SLOTS && i < ITEM_IDS_MAX; i++)
    {
        /* The Cradle key is tracked by its found bit only: carried as a
         * watch item it would meet Bunker 1's copy-the-key objective. */
        if (bondinvHasInvItem(i) && i != ITEM_GOLDENEYEKEY)
        {
            bitSet(s_snapWeapons, i);
        }
        if (bondinvHasDualWeapon(i, i))
        {
            bitSet(s_snapDuals, i);
        }
    }
    s_snapEquipped[0] = getCurrentPlayerWeaponId(GUNRIGHT);
    s_snapEquipped[1] = getCurrentPlayerWeaponId(GUNLEFT);
    for (i = 0; i < RANDO_AMMO_SLOTS; i++)
    {
        s_snapAmmo[i] = carriedAmmo(i) ? currentPlayerGetAmmoCount(i) : 0;
    }
    s_snapHealth = g_CurrentPlayer->bondhealth;
    s_snapArmour = g_CurrentPlayer->bondarmour;
    s_snapValid = TRUE;
}

static void commit(s32 withhealth);

void randoTick(void)
{
    RandoSave before;

    g_randoHighlightMsg = FALSE;   /* a pickup sets and uses it within one call */

    if (s_level < 0 || g_CurrentPlayer == NULL || g_CurrentPlayer->prop == NULL)
    {
        return;
    }
    if (g_CurrentPlayer->bonddead && !s_died)
    {
        s_died = TRUE;
        RANDOLOG("    DIED on %s\n", s_levelNames[s_level]);
    }
    if (s_tickCount == 300 && g_CameraMode == CAMERAMODE_FP)
    {
        /* Five seconds into play: are the items we handed over really held? */
        s32 i, held = 0, carried = 0;

        for (i = 0; i < s_ntracked; i++)
        {
            ObjectRecord *rec = s_tracked[i].rec;

            if (!s_tracked[i].carried || rec->type == PROPDEF_COLLECTABLE)
            {
                continue;   /* collectables become weapon-inventory items, not props */
            }
            carried++;
            if (rec->prop && bondinvHasPropInInv(rec->prop))
            {
                held++;
                if (rec->type == PROPDEF_KEY && ((KeyRecord *)rec)->keyflags != 0)
                {
                    RANDOLOG("    check #%d (key for this level): %s\n", s_tracked[i].item,
                             bondinvCheckHasKeyFlags(((KeyRecord *)rec)->keyflags) ? "opens its locks" : "locks NOT opened");
                }
            }
            else
            {
                RANDOLOG("    check #%d: NOT in inventory (prop %s)\n", s_tracked[i].item, rec->prop ? "present" : "none");
            }
        }
        RANDOLOG("    check: %d of %d carried items in the inventory\n", held, carried);
    }
    if (g_CameraMode != CAMERAMODE_FP && s_tickCount < 300)
    {
        return;   /* count play time from the end of the intro */
    }
    if (s_tickCount == 0 && g_ClockTimer != 0)
    {
        /* First frame of play: put items carried in from other levels straight
         * into the inventory, the way the game's own "Bond collects object" AI
         * command does. Leaving them at the start pad meant they could be
         * picked up during the intro cinema and not stick (Facility keycards,
         * 10-30 playtest). */
        s32 i;

        s_playStarted = TRUE;
        for (i = 0; i < s_ntracked; i++)
        {
            ObjectRecord *rec = s_tracked[i].rec;

            /* weapons and gadgets handed out at the start lie at Bond's feet and
             * are picked up the normal way once play starts: forcing a weapon
             * pickup here frees its prop under us (crashed, 10-31) */
            if ((s_tracked[i].carried || (s_tracked[i].atstart && rec->type != PROPDEF_COLLECTABLE))
                && rec->prop != NULL && !bondinvHasPropInInv(rec->prop))
            {
                TICKOP op = propPickupByPlayer(rec->prop, (s_seed.options & OPT_SHOW_HANDOVER) != 0);

                propExecuteTickOperation(rec->prop, op);
            }
        }
    }
    if ((s_tickCount++ % 15) != 0)
    {
        return;
    }

    snapshot();

    /* Weapons, ammo and the gun in hand persist through death and quitting
     * too, so write them as soon as they change. Health only moves on
     * completion. */
    before = s_save;
    commit(FALSE);
    if (memcmp(&before, &s_save, sizeof(s_save)) != 0)
    {
        randoIoWriteSave(&s_save);
    }
}

static void commit(s32 withhealth)
{
    s32 i;

    if (!s_snapValid)
    {
        return;
    }

    /* weapons only ever accumulate: a gadget the level took away stays owned */
    for (i = 0; i < RANDO_ITEM_SLOTS / 32; i++)
    {
        s_save.weapons[i] |= s_snapWeapons[i];
        s_save.duals[i] |= s_snapDuals[i];
    }
    memcpy(s_save.ammo, s_snapAmmo, sizeof(s_save.ammo));
    s_save.equipped[0] = s_snapEquipped[0];
    s_save.equipped[1] = s_snapEquipped[1];

    if (withhealth)
    {
        s_save.health = s_snapHealth > 0.0f ? s_snapHealth : 0.01f;
        s_save.armour = s_snapArmour;
    }
}

void randoStageLoad(s32 stage)
{
    if (s_level >= 0)
    {
        /* health and armour carry over on completion and on quitting;
         * dying returns you with what you came in with */
        commit(s_completed || !s_died);
        randoIoWriteSave(&s_save);
        RANDOLOG("<-- Leave %s: %s\n", s_levelNames[s_level],
                 s_completed ? "COMPLETED" : s_died ? "died (health stays as it was on entry)"
                                                    : "left without completing (health and armour kept)");
        logInventory("kept");
    }
    s_level = -1;
    s_died = FALSE;
    s_ntracked = 0;
    s_snapValid = FALSE;
}

s32 randoStageCompleted(s32 levelid)
{
    s32 before;

    if (!randoActive() || levelid < 0 || levelid >= RANDO_LEVELS)
    {
        return FALSE;
    }

    before = cradleUnlocked();
    if (levelid == s_level)
    {
        snapshot();
        s_completed = TRUE;
        commit(TRUE);
    }
    bitSet(&s_save.beaten, levelid);
    randoIoWriteSave(&s_save);

    {
        char open[256] = "";
        s32 lvl, nbeaten = 0, nlevels = 0;

        for (lvl = 0; lvl < RANDO_LEVELS; lvl++)
        {
            if (!levelEnabled(lvl))
            {
                continue;
            }
            nlevels++;
            nbeaten += bitGet(&s_save.beaten, lvl);
            if (!bitGet(&s_save.beaten, lvl) && levelUnlocked(lvl))
            {
                strcat(open, s_levelNames[lvl]);
                strcat(open, ", ");
            }
        }
        RANDOLOG("*** MISSION COMPLETE: %s (%d/%d levels beaten). Unlocked now: %s\n",
                 s_levelNames[levelid], nbeaten, nlevels, open[0] ? open : "none");
        if (!before && levelid != SP_LEVEL_CRADLE && cradleUnlocked())
        {
            RANDOLOG("*** CRADLE UNLOCKED (fanfare)\n");
        }
        if (levelid == SP_LEVEL_CRADLE)
        {
            RANDOLOG("*** CRADLE BEATEN: seed finished\n");
        }
    }

    return !before && levelid != SP_LEVEL_CRADLE && cradleUnlocked();
}

s32 randoSkipEmptyWeapon(s32 right, s32 left)
{
    s32 rtype, ltype;

    if (!randoActive() || s_level < 0 || right <= ITEM_FIST)
    {
        return FALSE;
    }
    rtype = get_ammo_type_for_weapon(right);
    if (rtype == 0 || currentPlayerGetAmmoCount(rtype) > 0)
    {
        return FALSE;
    }
    if (left > ITEM_FIST)
    {
        ltype = get_ammo_type_for_weapon(left);
        if (ltype == 0 || currentPlayerGetAmmoCount(ltype) > 0)
        {
            return FALSE;
        }
    }
    return TRUE;
}

s32 randoGuardDropAmmo(WeaponObjRecord *weapon, s32 qty)
{
    u8 *p = (u8 *)weapon;
    s32 onfloor;

    if (!randoActive() || s_level < 0 || qty <= 1)
    {
        return qty;   /* mines, grenades and other single pickups are unchanged */
    }

    /* A gun from the level's own records that no guard was carrying is a floor
     * pickup. Guard-carried guns keep PROPFLAG_ASSIGNEDTOCHR after they drop,
     * and guns scripts spawn on guards are allocated outside the records. */
    onfloor = p >= s_propBase && p < s_propEnd && !(weapon->flags & PROPFLAG_ASSIGNEDTOCHR);
    return onfloor ? qty : 5;
}

/* ------------------------------------------------------------ easy to spot */

#define GLOW_PERIOD  80        /* ticks (60 a second) per pulse */
#define GLOW_SIGHT   100.0f    /* model size the distance fade uses for glowing items: a guard's */
#define GLOW_MAX_SIZE 20.0f    /* only items smaller than this glow: keys, keycards, mines, bugs
                                * (12-15); briefcases and guns (26-40) are plain to see */
#define TINT_GOLD    ((255u << 24) | (200u << 16) | (40u << 8))
#define TINT_SAT     0xFFFFFF00u   /* white = saturation mode, alpha 128 = unchanged */
#define SAT_GREYER   83            /* about a third less colour */

/* 0 -> 255 -> 0 over GLOW_PERIOD ticks */
static s32 glowWave(void)
{
    s32 t = g_GlobalTimer % GLOW_PERIOD;

    return (t < GLOW_PERIOD / 2 ? t : GLOW_PERIOD - t) * 255 / (GLOW_PERIOD / 2);
}

static u32 itemTint(void)
{
    return TINT_GOLD | (u32)(80 + glowWave() * 120 / 255);
}

static u32 carrierTint(void)
{
    return (s_seed.options & OPT_CARRIER_GREYER) ? TINT_SAT | SAT_GREYER : 0;
}

/* Small items still to find on this level (and a crate holding one) pulse
 * gold, so a room can be checked from the doorway instead of walked. A guard
 * carrying one can be drawn slightly greyer (a setting), no glow. Found
 * from the live props every call, so it follows items guards drop. */
u32 randoGlow(PropRecord *prop)
{
    s32 i;

    if (s_level < 0 || prop == NULL || !(s_seed.options & (OPT_GLOW_ITEMS | OPT_CARRIER_GREYER)))
    {
        return 0;
    }
#ifdef PORT
    {
        /* GE_RANDO_GLOWALL=1: every prop and guard gets its tint (checks it renders) */
        static s32 all = -1;

        if (all < 0)
        {
            all = getenv("GE_RANDO_GLOWALL") != NULL;
        }
        if (all && (prop->type == PROP_TYPE_OBJ || prop->type == PROP_TYPE_WEAPON || prop->type == PROP_TYPE_CHR))
        {
            return prop->type == PROP_TYPE_CHR ? carrierTint() : itemTint();
        }
    }
#endif
    for (i = 0; i < s_ntracked; i++)
    {
        ObjectRecord *rec = s_tracked[i].rec;
        PropRecord *p = rec->prop;

        if (s_tracked[i].carried || itemFound(s_tracked[i].item) || p == NULL || p->obj != rec)
        {
            continue;
        }
        if (p == prop && rec->model != NULL && getinstsize(rec->model) >= GLOW_MAX_SIZE)
        {
            return 0;   /* briefcases, guns: easy enough to see as they are */
        }
        if (p == prop || (p->parent == prop && prop->type != PROP_TYPE_CHR))
        {
            return (s_seed.options & OPT_GLOW_ITEMS) ? itemTint() : 0;
        }
        if (p->parent == prop)
        {
            return carrierTint();
        }
    }
    return 0;
}

/* Wrap a model's display list in the PC renderer's tint (fast3d's otherwise
 * unused grayscale extension, see gfx_opengl.cpp): a colour mixes the model
 * toward bright gold by its alpha; white changes its saturation instead. The
 * model's shade colour can't do this: level fog and room lighting decide how
 * much of it shows. N64 builds draw it unchanged. */
#define GLOW_SETGRAYSCALE_EXT  0x39   /* port/fast3d/gbiex.h G_SETGRAYSCALE_EXT */
#define GLOW_SETINTENSITY_EXT  0x40   /* G_SETINTENSITY_EXT: tint colour and amount */

Gfx *randoGlowBegin(Gfx *gdl, u32 tint)
{
#ifdef PORT
    if (tint != 0)
    {
        gDma0p(gdl++, GLOW_SETINTENSITY_EXT, tint, 0);
        gDma0p(gdl++, GLOW_SETGRAYSCALE_EXT, 1, 0);
    }
#endif
    return gdl;
}

Gfx *randoGlowEnd(Gfx *gdl, u32 tint)
{
#ifdef PORT
    if (tint != 0)
    {
        gDma0p(gdl++, GLOW_SETGRAYSCALE_EXT, 0, 0);
    }
#endif
    return gdl;
}

/* Small models fade out at short range (keycards vanish across a room). */
f32 randoSightSize(PropRecord *prop, f32 size)
{
    return (size < GLOW_SIGHT && randoGlow(prop) != 0) ? GLOW_SIGHT : size;
}

s32 randoStageStatus(s32 levelid, s32 difficulty, s32 *status)
{
    if (!randoActive())
    {
        return FALSE;
    }

    if (levelid < 0 || levelid >= RANDO_LEVELS || difficulty != s_seed.difficulty)
    {
        *status = STAGESTATUS_LOCKED;
    }
    else if (bitGet(&s_save.beaten, levelid))
    {
        *status = STAGESTATUS_COMPLETED;
    }
    else if (levelUnlocked(levelid))
    {
        *status = STAGESTATUS_UNLOCKED;
    }
    else
    {
        *status = STAGESTATUS_LOCKED;
    }
    return TRUE;
}

/* ------------------------------------------------------------ platform I/O */

#ifdef PORT
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <time.h>
#include "system.h"
#include "fs.h"

static void randoLog(const char *fmt, ...)
{
    static char path[64];
    char line[512];
    char stamp[32];
    time_t now = time(NULL);
    va_list ap;
    FILE *f;

    va_start(ap, fmt);
    vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);

    if (getenv("GE_RANDOLOG"))
    {
        osSyncPrintf("RANDO: %s", line);
    }
    if (!s_seed.tried)
    {
        return;
    }

    snprintf(path, sizeof(path), "$S/rando/log-%08x%08x.txt", s_seed.seedhi, s_seed.seedlo);
    f = fopen(sysResolvePath(path), "a");
    if (f != NULL)
    {
        strftime(stamp, sizeof(stamp), "%Y-%m-%d %H:%M:%S", localtime(&now));
        fprintf(f, "%s  %s", stamp, line);
        fclose(f);
    }
}

static s32 randoIoLoadSeed(u8 *buf, s32 max)
{
    FSFile *f = fsOpen(sysResolvePath("$S/rando/seed.bin"), "rb");
    s32 n;

    if (f == NULL)
    {
        return 0;
    }
    n = fsRead(f, buf, max);
    fsClose(f);
    return n;
}

static const char *savePath(void)
{
    static char name[64];

    snprintf(name, sizeof(name), "$S/rando/save-%08x%08x.bin", s_seed.seedhi, s_seed.seedlo);
    return sysResolvePath(name);
}

static s32 randoIoLoadSave(RandoSave *save)
{
    FSFile *f = fsOpen(savePath(), "rb");
    s32 n;

    if (f == NULL)
    {
        return FALSE;
    }
    n = fsRead(f, save, sizeof(*save));
    fsClose(f);
    return n == (s32)sizeof(*save);
}

static void randoIoWriteSave(const RandoSave *save)
{
    FSFile *f = fsOpen(savePath(), "wb");

    if (f != NULL)
    {
        fsWrite(f, save, sizeof(*save));
        fsClose(f);
    }
}
#else
/* N64: seed blob in ROM + save in EEPROM -- not wired yet */
static s32 randoIoLoadSeed(u8 *buf, s32 max) { return 0; }
static s32 randoIoLoadSave(RandoSave *save) { return FALSE; }
static void randoIoWriteSave(const RandoSave *save) { }
static void randoLog(const char *fmt, ...) { }
#endif

#endif /* GE_RANDOMIZER */
