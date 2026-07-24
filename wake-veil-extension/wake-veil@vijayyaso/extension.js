// Wake Veil: on suspend, place a blurred veil over the whole stage so the
// first frame composited after resume is a clean blurred desktop instead of
// a half-drawn one; fade the veil out once the session has settled.

import St from 'gi://St';
import GLib from 'gi://GLib';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as LoginManager from 'resource:///org/gnome/shell/misc/loginManager.js';

const SETTLE_MS = 900;    // how long after resume before the veil starts fading
const FADE_MS = 600;      // fade-out duration
const FAILSAFE_MS = 8000; // hard ceiling: veil is always destroyed by this age

export default class WakeVeilExtension {
    enable() {
        this._veil = null;
        this._timeouts = [];
        this._loginManager = LoginManager.getLoginManager();
        this._sleepId = this._loginManager.connect(
            'prepare-for-sleep', (_lm, aboutToSuspend) => {
                if (aboutToSuspend)
                    this._showVeil();
                else
                    this._scheduleFade(SETTLE_MS);
            });
    }

    disable() {
        if (this._sleepId) {
            this._loginManager.disconnect(this._sleepId);
            this._sleepId = null;
        }
        this._clearTimeouts();
        this._destroyVeil();
        this._loginManager = null;
    }

    _addTimeout(ms, fn) {
        const id = GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => {
            this._timeouts = this._timeouts.filter(t => t !== id);
            fn();
            return GLib.SOURCE_REMOVE;
        });
        this._timeouts.push(id);
    }

    _clearTimeouts() {
        for (const id of this._timeouts)
            GLib.source_remove(id);
        this._timeouts = [];
    }

    _showVeil() {
        if (this._veil)
            return;
        // A plain opaque veil: a live BlurEffect at this resolution costs
        // several seconds per frame on the Iris Pro (measured 2026-07-24),
        // so we fade from black like macOS does instead.
        this._veil = new St.Widget({
            style: 'background-color: rgb(0, 0, 0);',
            reactive: false,
            width: global.stage.width,
            height: global.stage.height,
        });
        Main.uiGroup.add_child(this._veil);
        // Failsafe: never allow a stuck veil, whatever happens around resume.
        this._addTimeout(FAILSAFE_MS, () => this._destroyVeil());
    }

    _scheduleFade(delayMs) {
        if (!this._veil)
            return;
        this._addTimeout(delayMs, () => {
            if (!this._veil)
                return;
            this._veil.ease({
                opacity: 0,
                duration: FADE_MS,
                mode: Clutter.AnimationMode.EASE_OUT_QUAD,
                onComplete: () => this._destroyVeil(),
            });
        });
    }

    _destroyVeil() {
        if (this._veil) {
            this._veil.destroy();
            this._veil = null;
        }
    }
}
