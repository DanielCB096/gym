import type { ConfigContext, ExpoConfig } from "expo/config";

// Una build release de Android bloquea el HTTP en claro. La vista previa
// necesita hablar con el backend por la LAN, así que el permiso viaja solo
// cuando ALLOW_CLEARTEXT=true (perfil preview de eas.json).
//
// GOOGLE_SERVICES_JSON llega como variable de archivo de EAS: no vive en el
// repositorio, y solo se usa cuando el build la materializa.
export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: config.name ?? "Centro Fit Socio",
  slug: config.slug ?? "centro-fit-socio",
  ios: {
    ...config.ios,
    infoPlist: {
      ...config.ios?.infoPlist,
      ...(process.env.ALLOW_CLEARTEXT === "true"
        ? {
            NSAppTransportSecurity: {
              NSAllowsLocalNetworking: true,
              NSAllowsArbitraryLoads: false,
            },
          }
        : {}),
    },
  },
  android: {
    ...config.android,
    ...(process.env.GOOGLE_SERVICES_JSON
      ? { googleServicesFile: process.env.GOOGLE_SERVICES_JSON }
      : {}),
  },
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
