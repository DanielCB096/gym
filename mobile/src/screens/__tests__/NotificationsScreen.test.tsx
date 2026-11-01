import { fireEvent, render, screen } from "@testing-library/react-native";
import { beforeEach, describe, expect, it, jest } from "@jest/globals";

import {
  getMemberNotificationPreferences,
  getMemberNotifications,
  updateMemberNotificationPreferences,
} from "../../api";
import type {
  MemberNotificationPage,
  MemberNotificationPreferences,
} from "../../types";
import { NotificationsScreen } from "../NotificationsScreen";

jest.setTimeout(15_000);

jest.mock("../../api", () => {
  const actual =
    jest.requireActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    getMemberNotificationPreferences: jest.fn(),
    getMemberNotifications: jest.fn(),
    updateMemberNotificationPreferences: jest.fn(),
  };
});

jest.mock("../../pushProbe", () => ({
  PUSH_PROBE_ENABLED: false,
  scheduleLocalPushProbe: jest.fn(),
}));

const notificationPage: MemberNotificationPage = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
  pages: 0,
  unread_total: 0,
};

const notificationPreferences: MemberNotificationPreferences = {
  items: [
    {
      category: "membership",
      push_enabled: false,
      email_enabled: false,
      updated_at: null,
    },
  ],
  email_available: true,
  quiet_hours: null,
  club_quiet_hours: null,
};

let rejectPreferenceUpdate: ((reason: unknown) => void) | null = null;

describe("NotificationsScreen preference failures", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    rejectPreferenceUpdate = null;
    jest.mocked(getMemberNotifications).mockResolvedValue(notificationPage);
    jest
      .mocked(getMemberNotificationPreferences)
      .mockResolvedValue(notificationPreferences);
    jest
      .mocked(updateMemberNotificationPreferences)
      .mockImplementation(
        () =>
          new Promise((_resolve, reject) => {
            rejectPreferenceUpdate = reject;
          }),
      );
  });

  it("restores the previous email switch state and exposes the error as a polite live region", async () => {
    render(
      <NotificationsScreen
        token="test-token"
        onBack={jest.fn()}
        onSessionExpired={jest.fn()}
        onUnreadChange={jest.fn()}
        onOpenDestination={jest.fn()}
      />,
    );

    const preferenceName = "Avisos de Membresía por correo";
    const emailSwitch = await screen.findByRole("switch", {
      name: preferenceName,
    });

    fireEvent(emailSwitch, "valueChange", true);

    await waitForPreferenceValue(preferenceName, true);
    expect(
      screen.getByRole("switch", { name: preferenceName }).props.disabled,
    ).toBe(true);
    if (!rejectPreferenceUpdate) {
      throw new Error("Preference update did not start");
    }
    rejectPreferenceUpdate(new TypeError("Network request failed"));

    const error = await screen.findByText(
      "Ocurrió un error inesperado. Intenta de nuevo.",
    );

    expect(screen.getByRole("switch", { name: preferenceName }).props.value).toBe(false);
    expect(error.props.accessibilityLiveRegion).toBe("polite");
    expect(updateMemberNotificationPreferences).toHaveBeenCalledTimes(1);
  });
});

async function waitForPreferenceValue(name: string, value: boolean) {
  await screen.findByRole("switch", { name, checked: value });
}
