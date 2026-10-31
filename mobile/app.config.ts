import type { ConfigContext, ExpoConfig } from "expo/config";

// Una build release de Android bloquea el HTTP en claro. La vista previa
// necesita hablar con el backend por la LAN, así que el permiso viaja solo
// cuando ALLOW_CLEARTEXT=true (perfil preview de eas.json).
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: config.name ?? "Centro Fit Socio",
  slug: config.slug ?? "centro-fit-socio",
  plugins: [
    ...(config.plugins ?? []),
    [
      "expo-build-properties",
      {
        android: {
          usesCleartextTraffic: process.env.ALLOW_CLEARTEXT === "true",
        },
      },
    ],
  ],
});
