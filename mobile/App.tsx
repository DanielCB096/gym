import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, SafeAreaView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

import {
  ApiError,
  getMemberProfile,
  getUnreadNotificationCount,
  logoutMember,
  markMemberNotificationRead,
} from "./src/api";
import { describeError } from "./src/errors";
import { AccessCodeScreen } from "./src/screens/AccessCodeScreen";
import { ClassesScreen } from "./src/screens/ClassesScreen";
import { CodeScreen } from "./src/screens/CodeScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { LoginScreen } from "./src/screens/LoginScreen";
import { NotificationsScreen } from "./src/screens/NotificationsScreen";
import { PaymentsScreen } from "./src/screens/PaymentsScreen";
import { PhysioScreen } from "./src/screens/PhysioScreen";
import { ProgressPhotosScreen } from "./src/screens/ProgressPhotosScreen";
import { RoutineDetailScreen } from "./src/screens/RoutineDetailScreen";
import { RoutinesScreen } from "./src/screens/RoutinesScreen";
import { clearToken, loadToken, saveToken } from "./src/storage";
import {
  registerPushForSession,
  subscribePushTaps,
  unregisterPushForSession,
  type PushTap,
} from "./src/push";
import {
  notificationDestination,
  notificationFocus,
  type NotificationDestination,
  type NotificationFocus,
} from "./src/notificationRouting";
import { colors } from "./src/theme";
import type { MemberLoginResult, MemberProfile } from "./src/types";

type Stage =
  | "restoring"
  | "email"
  | "code"
  | "home"
  | "accessCode"
  | "classes"
  | "physio"
  | "routines"
  | "routineDetail"
  | "progressPhotos"
  | "payments"
  | "notifications";

export default function App() {
  const [stage, setStage] = useState<Stage>("restoring");
  const [email, setEmail] = useState("");
  const [previewCode, setPreviewCode] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [profile, setProfile] = useState<MemberProfile | null>(null);
  const [fallbackName, setFallbackName] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginNotice, setLoginNotice] = useState<string | null>(null);
  const [homeError, setHomeError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [focus, setFocus] = useState<NotificationFocus | null>(null);
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const tokenRef = useRef<string | null>(null);
  const pendingPushRef = useRef<PushTap | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const stored = await loadToken();
      if (!active) {
        return;
      }
      if (!stored) {
        setStage("email");
        return;
      }
      try {
        const next = await getMemberProfile(stored);
        if (!active) {
          return;
        }
        tokenRef.current = stored;
        setToken(stored);
        setProfile(next);
        setFallbackName(next.first_name);
        setStage(takePendingStage(stored));
        void refreshUnreadNotifications(stored);
        void registerPushForSession(stored);
      } catch (error) {
        if (!active) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          await clearToken();
          pendingPushRef.current = null;
          setLoginNotice("Tu sesión expiró. Vuelve a entrar.");
        } else {
          setLoginError(describeError(error));
        }
        setStage("email");
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function refreshUnreadNotifications(activeToken: string) {
    try {
      setUnreadNotifications(await getUnreadNotificationCount(activeToken));
    } catch {
      // The badge is optional; the inbox reports the real count when it is opened.
    }
  }

  function openPushTap(tap: PushTap, activeToken: string): Stage {
    const destination = notificationDestination(tap.kind ?? "");
    setFocus(notificationFocus(tap.kind ?? "", tap.refId));
    if (destination !== "notifications" && tap.notificationId) {
      void markMemberNotificationRead(activeToken, tap.notificationId)
        .then(() => refreshUnreadNotifications(activeToken))
        .catch(() => {
          // The notice stays unread; the inbox fixes it when it is opened.
        });
    }
    return destination;
  }

  function takePendingStage(activeToken: string): Stage {
    const pending = pendingPushRef.current;
    pendingPushRef.current = null;
    return pending ? openPushTap(pending, activeToken) : "home";
  }

  useEffect(() => {
    let active = true;
    let dispose: (() => void) | undefined;
    void subscribePushTaps((tap) => {
      const activeToken = tokenRef.current;
      if (!activeToken) {
        pendingPushRef.current = tap;
        return;
      }
      setStage(openPushTap(tap, activeToken));
    }).then((cleanup) => {
      if (active) {
        dispose = cleanup;
      } else {
        cleanup();
      }
    });
    return () => {
      active = false;
      dispose?.();
    };
  }, []);

  function handleCodeRequested(nextEmail: string, nextPreviewCode: string | null) {
    setEmail(nextEmail);
    setPreviewCode(nextPreviewCode);
    setLoginError(null);
    setLoginNotice(null);
    setStage("code");
  }

  async function handleAuthenticated(result: MemberLoginResult) {
    tokenRef.current = result.access_token;
    setToken(result.access_token);
    setFallbackName(result.member.first_name);
    setHomeError(null);
    await saveToken(result.access_token);
    setStage(takePendingStage(result.access_token));
    void refreshUnreadNotifications(result.access_token);
    void registerPushForSession(result.access_token);
    try {
      const next = await getMemberProfile(result.access_token);
      setProfile(next);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        tokenRef.current = null;
        pendingPushRef.current = null;
        await clearToken();
        setToken(null);
        setFocus(null);
        setStage("email");
        setLoginNotice("Tu sesión expiró. Vuelve a entrar.");
        return;
      }
      setHomeError(describeError(error));
    }
  }

  async function handleRefresh() {
    if (!token || refreshing) {
      return;
    }
    setRefreshing(true);
    setHomeError(null);
    try {
      const next = await getMemberProfile(token);
      setProfile(next);
      setFallbackName(next.first_name);
      await refreshUnreadNotifications(token);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        tokenRef.current = null;
        pendingPushRef.current = null;
        await clearToken();
        setToken(null);
        setProfile(null);
        setFocus(null);
        setStage("email");
        setLoginNotice("Tu sesión expiró. Vuelve a entrar.");
      } else {
        setHomeError(describeError(error));
      }
    } finally {
      setRefreshing(false);
    }
  }

  async function handleLogout() {
    const activeToken = token;
    tokenRef.current = null;
    pendingPushRef.current = null;
    await clearToken();
    setToken(null);
    setProfile(null);
    setFallbackName(null);
    setEmail("");
    setPreviewCode(null);
    setHomeError(null);
    setLoginError(null);
    setLoginNotice(null);
    setUnreadNotifications(0);
    setFocus(null);
    setStage("email");
    if (activeToken) {
      await unregisterPushForSession(activeToken);
      try {
        await logoutMember(activeToken);
      } catch {
        // The local session is already gone; the server copy expires on its own.
      }
    }
  }

  function handleBackToEmail() {
    setStage("email");
    setPreviewCode(null);
  }

  function openSection(next: Stage) {
    setFocus(null);
    setStage(next);
  }

  function handleBackHome() {
    openSection("home");
  }

  function focusRefFor(destination: NotificationDestination): string | null {
    return focus && focus.destination === destination ? focus.refId : null;
  }

  function handleOpenDestination(kind: string, refId: string | null) {
    const destination = notificationDestination(kind);
    if (destination === "notifications") {
      return;
    }
    setFocus(notificationFocus(kind, refId));
    setStage(destination);
  }

  function handleOpenClasses() {
    openSection("classes");
  }

  function handleOpenPhysio() {
    openSection("physio");
  }

  function handleOpenAccessCode() {
    openSection("accessCode");
  }

  function handleOpenRoutines() {
    openSection("routines");
  }

  function handleOpenRoutine(assignmentId: string) {
    setFocus(null);
    setSelectedAssignmentId(assignmentId);
    setStage("routineDetail");
  }

  function handleOpenProgressPhotos() {
    setFocus(null);
    setStage("progressPhotos");
  }

  function handleOpenPayments() {
    openSection("payments");
  }

  function handleOpenNotifications() {
    openSection("notifications");
  }

  async function handleSessionExpired() {
    tokenRef.current = null;
    pendingPushRef.current = null;
    await clearToken();
    setToken(null);
    setProfile(null);
    setFallbackName(null);
    setHomeError(null);
    setUnreadNotifications(0);
    setFocus(null);
    setLoginNotice("Tu sesión expiró. Vuelve a entrar.");
    setStage("email");
  }

  return (
    <View style={styles.root}>
      <SafeAreaView style={styles.safeArea}>
        <StatusBar style="light" />
        {stage === "restoring" ? (
          <View style={styles.loading}>
            <View style={styles.brandDot} />
            <Text style={styles.loadingBrand}>CENTRO FIT</Text>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : null}
        {stage === "email" ? (
          <LoginScreen
            initialError={loginError}
            notice={loginNotice}
            onCodeRequested={handleCodeRequested}
          />
        ) : null}
        {stage === "code" ? (
          <CodeScreen
            email={email}
            previewCode={previewCode}
            onBack={handleBackToEmail}
            onAuthenticated={handleAuthenticated}
          />
        ) : null}
        {stage === "home" ? (
          <HomeScreen
            profile={profile}
            fallbackName={fallbackName}
            refreshing={refreshing}
            error={homeError}
            onRefresh={handleRefresh}
            onLogout={handleLogout}
            onOpenAccessCode={handleOpenAccessCode}
            onOpenClasses={handleOpenClasses}
            onOpenPhysio={handleOpenPhysio}
            onOpenRoutines={handleOpenRoutines}
            onOpenPayments={handleOpenPayments}
            unreadNotifications={unreadNotifications}
            onOpenNotifications={handleOpenNotifications}
          />
        ) : null}
        {stage === "accessCode" && token ? (
          <AccessCodeScreen
            token={token}
            onBack={handleBackHome}
            onSessionExpired={() => void handleSessionExpired()}
          />
        ) : null}
        {stage === "classes" && token ? (
          <ClassesScreen
            token={token}
            focusRefId={focusRefFor("classes")}
            onBack={handleBackHome}
            onSessionExpired={() => void handleSessionExpired()}
          />
        ) : null}
        {stage === "physio" && token ? (
          <PhysioScreen
            token={token}
            focusRefId={focusRefFor("physio")}
            onBack={handleBackHome}
            onSessionExpired={() => void handleSessionExpired()}
          />
        ) : null}
        {stage === "routines" && token ? (
          <RoutinesScreen
            token={token}
            focusRefId={focusRefFor("routines")}
            onBack={handleBackHome}
            onOpenRoutine={handleOpenRoutine}
            onOpenPhotos={handleOpenProgressPhotos}
            onSessionExpired={() => void handleSessionExpired()}
          />
        ) : null}
        {stage === "progressPhotos" && token ? (
          <ProgressPhotosScreen
            token={token}
            onBack={() => setStage("routines")}
            onSessionExpired={() => void handleSessionExpired()}
          />
        ) : null}
        {stage === "routineDetail" && token && selectedAssignmentId ? (
          <RoutineDetailScreen
            token={token}
            assignmentId={selectedAssignmentId}
            onBack={() => setStage("routines")}
            onSessionExpired={() => void handleSessionExpired()}
          />
        ) : null}
        {stage === "payments" && token ? (
          <PaymentsScreen
            token={token}
            onBack={handleBackHome}
            onSessionExpired={() => void handleSessionExpired()}
          />
        ) : null}
        {stage === "notifications" && token ? (
          <NotificationsScreen
            token={token}
            onBack={handleBackHome}
            onSessionExpired={() => void handleSessionExpired()}
            onUnreadChange={setUnreadNotifications}
            onOpenDestination={handleOpenDestination}
          />
        ) : null}
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    backgroundColor: colors.background,
    flex: 1,
  },
  safeArea: {
    flex: 1,
  },
  loading: {
    alignItems: "center",
    flex: 1,
    gap: 16,
    justifyContent: "center",
  },
  brandDot: {
    backgroundColor: colors.accent,
    borderRadius: 8,
    height: 16,
    width: 16,
  },
  loadingBrand: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "800",
    letterSpacing: 3,
  },
});
