import { useEffect, useState } from "react";
import { ActivityIndicator, SafeAreaView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

import { ApiError, getMemberProfile, logoutMember } from "./src/api";
import { describeError } from "./src/errors";
import { CodeScreen } from "./src/screens/CodeScreen";
import { HomeScreen } from "./src/screens/HomeScreen";
import { LoginScreen } from "./src/screens/LoginScreen";
import { clearToken, loadToken, saveToken } from "./src/storage";
import { colors } from "./src/theme";
import type { MemberLoginResult, MemberProfile } from "./src/types";

type Stage = "restoring" | "email" | "code" | "home";

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
        setToken(stored);
        setProfile(next);
        setFallbackName(next.first_name);
        setStage("home");
      } catch (error) {
        if (!active) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          await clearToken();
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

  function handleCodeRequested(nextEmail: string, nextPreviewCode: string | null) {
    setEmail(nextEmail);
    setPreviewCode(nextPreviewCode);
    setLoginError(null);
    setLoginNotice(null);
    setStage("code");
  }

  async function handleAuthenticated(result: MemberLoginResult) {
    setToken(result.access_token);
    setFallbackName(result.member.first_name);
    setHomeError(null);
    await saveToken(result.access_token);
    setStage("home");
    try {
      const next = await getMemberProfile(result.access_token);
      setProfile(next);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await clearToken();
        setToken(null);
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
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        await clearToken();
        setToken(null);
        setProfile(null);
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
    await clearToken();
    setToken(null);
    setProfile(null);
    setFallbackName(null);
    setEmail("");
    setPreviewCode(null);
    setHomeError(null);
    setLoginError(null);
    setLoginNotice(null);
    setStage("email");
    if (activeToken) {
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
