package org.cabinetapp.cabinet.notifications;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

public final class NotificationScheduler {
    private static final String PREFS_NAME = "cabinet_dose_notifications";
    private static final String ALARMS_KEY = "alarms";
    private static final String CHANNEL_ID = "medicine_dose_reminders";
    private static final int MAX_ACTIVE_ALARMS = 400;

    private NotificationScheduler() {}

    public static boolean hasNotificationPermission(Context context) {
        return Build.VERSION.SDK_INT < 33
            || context.checkSelfPermission("android.permission.POST_NOTIFICATIONS")
                == PackageManager.PERMISSION_GRANTED;
    }

    public static synchronized void replaceAll(Context context, String alarmJson) {
        Context appContext = context.getApplicationContext();
        cancelStoredAlarms(appContext);
        try {
            JSONArray incoming = new JSONArray(alarmJson);
            JSONArray alarms = new JSONArray();
            long now = System.currentTimeMillis();
            for (int i = 0; i < incoming.length(); i++) {
                JSONObject source = incoming.getJSONObject(i);
                if (source.getLong("at") <= now) {
                    continue;
                }
                JSONObject alarm = new JSONObject(source.toString());
                alarm.put("scheduled", false);
                alarms.put(alarm);
            }
            saveAlarms(appContext, alarms);
            scheduleAvailableAlarms(appContext, alarms);
        } catch (JSONException error) {
            throw new IllegalArgumentException("Invalid Cabinet dose alarm data.", error);
        }
    }

    static synchronized void restoreAfterBoot(Context context) {
        Context appContext = context.getApplicationContext();
        JSONArray alarms = readAlarms(appContext);
        JSONArray futureAlarms = new JSONArray();
        long now = System.currentTimeMillis();
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null || alarm.optLong("at") <= now) {
                continue;
            }
            alarm.remove("scheduled");
            try {
                alarm.put("scheduled", false);
                futureAlarms.put(alarm);
            } catch (JSONException error) {
                throw new IllegalStateException("Couldn't restore dose reminders.", error);
            }
        }
        saveAlarms(appContext, futureAlarms);
        scheduleAvailableAlarms(appContext, futureAlarms);
    }

    static synchronized void onAlarm(Context context, int reminderId) {
        Context appContext = context.getApplicationContext();
        JSONArray alarms = readAlarms(appContext);
        JSONObject firedAlarm = null;
        JSONArray remaining = new JSONArray();
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            if (alarm.optInt("id", -1) == reminderId) {
                firedAlarm = alarm;
            } else {
                remaining.put(alarm);
            }
        }
        saveAlarms(appContext, remaining);
        if (firedAlarm != null) {
            postNotification(
                appContext,
                reminderId,
                firedAlarm.optString("title", "Medicine reminder"),
                firedAlarm.optString("message", "It is time for a scheduled dose.")
            );
        }
        scheduleAvailableAlarms(appContext, remaining);
    }

    private static void scheduleAvailableAlarms(Context context, JSONArray alarms) {
        int scheduledCount = 0;
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm != null && alarm.optBoolean("scheduled", false)) {
                scheduledCount++;
            }
        }
        for (int i = 0; i < alarms.length() && scheduledCount < MAX_ACTIVE_ALARMS; i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null || alarm.optBoolean("scheduled", false)) {
                continue;
            }
            long triggerAt = alarm.optLong("at");
            if (triggerAt <= System.currentTimeMillis()) {
                continue;
            }
            int id = alarm.optInt("id", -1);
            if (id == -1 || id == Integer.MIN_VALUE) {
                continue;
            }
            scheduleAlarm(context, id, triggerAt, alarm);
            try {
                alarm.put("scheduled", true);
            } catch (JSONException error) {
                throw new IllegalStateException("Couldn't queue a dose reminder.", error);
            }
            scheduledCount++;
        }
        saveAlarms(context, alarms);
    }

    private static void scheduleAlarm(
        Context context, int id, long triggerAt, JSONObject alarm
    ) {
        AlarmManager manager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        Intent intent = new Intent(context, DoseAlarmReceiver.class);
        intent.putExtra("reminder_id", id);
        intent.putExtra("title", alarm.optString("title", "Medicine reminder"));
        intent.putExtra("message", alarm.optString("message", "It is time for a scheduled dose."));
        PendingIntent pendingIntent = PendingIntent.getBroadcast(
            context,
            id,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            manager.setAndAllowWhileIdle(
                AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent
            );
        } else {
            manager.set(AlarmManager.RTC_WAKEUP, triggerAt, pendingIntent);
        }
    }

    private static void cancelStoredAlarms(Context context) {
        JSONArray alarms = readAlarms(context);
        AlarmManager manager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        for (int i = 0; i < alarms.length(); i++) {
            JSONObject alarm = alarms.optJSONObject(i);
            if (alarm == null) {
                continue;
            }
            int id = alarm.optInt("id", -1);
            if (id == -1 || id == Integer.MIN_VALUE) {
                continue;
            }
            PendingIntent pendingIntent = PendingIntent.getBroadcast(
                context,
                id,
                new Intent(context, DoseAlarmReceiver.class),
                PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE
            );
            if (pendingIntent != null) {
                manager.cancel(pendingIntent);
                pendingIntent.cancel();
            }
        }
    }

    private static JSONArray readAlarms(Context context) {
        String value = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .getString(ALARMS_KEY, "[]");
        try {
            return new JSONArray(value);
        } catch (JSONException error) {
            throw new IllegalStateException("Stored dose reminders are unreadable.", error);
        }
    }

    private static void saveAlarms(Context context, JSONArray alarms) {
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            .edit()
            .putString(ALARMS_KEY, alarms.toString())
            .apply();
    }

    private static void postNotification(
        Context context, int id, String title, String message
    ) {
        NotificationManager manager =
            (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Medicine dose reminders",
                NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Alerts for medicine doses you scheduled in Cabinet.");
            manager.createNotificationChannel(channel);
        }
        if (!hasNotificationPermission(context)) {
            return;
        }
        Intent launchIntent = context.getPackageManager()
            .getLaunchIntentForPackage(context.getPackageName());
        PendingIntent contentIntent = launchIntent == null ? null : PendingIntent.getActivity(
            context,
            id,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? new Notification.Builder(context, CHANNEL_ID)
            : new Notification.Builder(context);
        builder.setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
            .setContentTitle(title)
            .setContentText(message)
            .setStyle(new Notification.BigTextStyle().bigText(message))
            .setAutoCancel(true)
            .setCategory(Notification.CATEGORY_REMINDER)
            .setPriority(Notification.PRIORITY_HIGH);
        if (contentIntent != null) {
            builder.setContentIntent(contentIntent);
        }
        manager.notify(id, builder.build());
    }
}
