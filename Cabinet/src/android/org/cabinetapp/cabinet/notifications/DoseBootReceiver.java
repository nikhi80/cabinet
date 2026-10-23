package org.cabinetapp.cabinet.notifications;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class DoseBootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            NotificationScheduler.restoreAfterBoot(context);
        }
    }
}
