package org.cabinetapp.cabinet.notifications;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class DoseAlarmReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        NotificationScheduler.onAlarm(
            context,
            intent.getIntExtra("reminder_id", -1)
        );
    }
}
