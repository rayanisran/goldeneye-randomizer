#ifndef _RANDO_H_
#define _RANDO_H_

/*
 * GoldenEye randomizer runtime (feature/randomizer).
 *
 * A seed file written by `python -m randomizer.generate` says where every
 * shuffled item lives. Vanilla setup data is never edited on disk: items are
 * moved, hidden or added to the level's propDefs in RAM at load time, so the
 * same code works for the PC port and a future N64 build (only the seed/save
 * I/O at the bottom of rando.c is platform-specific).
 *
 * Inactive (every hook is a no-op) unless a seed is present.
 */

#include <ultra64.h>
#include <bondtypes.h>

#ifdef GE_RANDOMIZER

/* TRUE when a seed is loaded. Loads seed + save on first call. */
s32  randoActive(void);

/* prop.c setupLoad: after the setup file is rebased, before props spawn. */
void randoPatchSetup(s32 stageId);

/* bondview_r.c: TRUE = skip the level's own start weapons/ammo. */
s32  randoSkipVanillaLoadout(void);
/* bondview_r.c: give the carried inventory, health and armour, and start
 * with whatever was in hand when the last level ended. */
void randoApplyLoadout(s32 *startright, s32 *startleft, s32 *setstarting);

/* propobj.c propPickupByPlayer: TRUE = refuse this pickup for now (items carried
 * in from other levels are handed over when play starts, not during the intro). */
s32  randoBlockPickup(ObjectRecord *obj);

/* propobj.c propPickupByPlayer: marks shuffled items found. Returns the
 * pickup message for items the randomizer added, else NULL. */
char *randoOnPickup(ObjectRecord *obj);

/* lv.c lvlManageMpGame: once per frame. */
void randoTick(void);

/* lv.c lvlStageLoad: commit the finished level's inventory to the save. */
void randoStageLoad(s32 stage);

/* file.c end_of_mission_briefing: level beaten. TRUE = Cradle just unlocked
 * (play the "new cheat unlocked" fanfare). */
s32  randoStageCompleted(s32 levelid);

/* file2.c fileIsStageUnlockedAtDifficulty: TRUE = *status was decided. */
s32  randoStageStatus(s32 levelid, s32 difficulty, s32 *status);

/* Best times belong to the seed (a new seed starts with none); the save
 * folder's own times are left alone. front.c mission status: this level's best
 * in seconds, 0 = none yet, -1 = no seed loaded (use the folder's).
 * file2.c, a level's time saved: it was finished in `seconds`. */
s32  randoBestTime(s32 levelid);
void randoRecordTime(s32 levelid, s32 seconds);

/* bondinv.c watch inventory: name for a record the randomizer added, else NULL. */
char *randoInvName(ObjectRecord *obj);

/* port optionsoverlay.c: found items' short names for the menu list; -1 when
 * not on the menus of a randomizer seed. */
int  randoMenuItemNames(const char **names, int max);

/* port input.c: note controller drops/returns in the progress log. */
void randoLogEvent(const char *line);

/* propobj.c chrEquipWeapon: a guard is given a model that can't be held in
 * a hand (carried concealed instead); logged once per object. */
void randoNoteHeldGadget(ObjectRecord *obj, s32 chrnum);

/* prop.c setupLoad: extra inventory slots for the carried items. */
s32  randoExtraInvSlots(void);

/* gun.c weapon cycling: TRUE = skip this weapon (it uses ammo and none is left). */
s32  randoSkipEmptyWeapon(s32 right, s32 left);

/* propobj.c ammo_collected_from_weapon: guns dropped by guards give 5 rounds. */
s32  randoGuardDropAmmo(WeaponObjRecord *weapon, s32 qty);

/* propobj.c / chr.c rendering: the tint for this prop this frame (an item
 * still to find glows gold; a guard carrying one gets a saturation change),
 * 0 = none. */
u32  randoGlow(PropRecord *prop);
/* Around a model's draw: apply randoGlow's tint (0 emits nothing). */
Gfx *randoGlowBegin(Gfx *gdl, u32 tint);
Gfx *randoGlowEnd(Gfx *gdl, u32 tint);
/* propobj.c distance fade and culling: glowing items stay visible as far as a guard. */
f32  randoSightSize(PropRecord *prop, f32 size);

/* Set when a randomizer item is picked up; bondview2.c draws the next bottom
 * message in yellow and clears it. randoTick clears a stale flag each frame. */
extern s32 g_randoHighlightMsg;

/* Set by randoOnPickup for a silent handover of a carried item: propobj.c
 * skips the pickup sound. */
extern s32 g_randoSilentPickup;

#endif /* GE_RANDOMIZER */

#endif /* _RANDO_H_ */
