import AppKit
import RMirrorKit
import SwiftUI

/// The settings window: a few everyday options, one folded section for syncing details and one
/// for developers and self-hosters.
struct SettingsView: View {
    @EnvironmentObject private var store: AppStore

    @State private var loginEnabled = LoginItem.isEnabled
    @State private var loginNeedsApproval = LoginItem.needsApprovalInSystemSettings
    @State private var confirmingSignOut = false

    @State private var showMore = false
    @State private var limitEnabled = false
    @State private var limitText = ""
    @State private var limitError = false

    @State private var showDeveloper = false
    @State private var server: ServerChoice = .production
    @State private var customURL = ""
    @State private var urlError = false
    @State private var needsSignIn = false
    @State private var loadedFromSettings: AppSettings?

    enum ServerChoice: Hashable { case production, staging, custom }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                if let problem = store.settingsProblem {
                    Text(SharedCopy.problem(problem))
                        .font(Theme.Font.caption)
                        .foregroundStyle(Theme.danger)
                        .accessibilityLabel(SharedCopy.problem(problem))
                }
                if store.settings == nil {
                    HStack(spacing: Theme.Space.s) {
                        ProgressView().controlSize(.small)
                        Text(SettingsCopy.loading).font(Theme.Font.body).foregroundStyle(Theme.textSecondary)
                    }
                    .accessibilityElement(children: .combine)
                }
                general
                account
                if let settings = store.settings {
                    syncing(settings)
                    developer(settings)
                }
                footer
            }
            .padding(Theme.Space.l)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(width: 520, height: 460)
        .background(Theme.background)
        .foregroundStyle(Theme.text)
        .task {
            await store.loadSettings()
            syncFields()
        }
        .onChange(of: store.settings) { _ in syncFields() }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            refreshLoginItem()
        }
    }

    // MARK: General

    private var general: some View {
        section(SettingsCopy.generalHeading) {
            HStack {
                Text(SettingsCopy.openAtLogin).font(Theme.Font.body)
                Spacer()
                Toggle(SettingsCopy.openAtLogin, isOn: Binding(
                    get: { loginEnabled },
                    set: { newValue in
                        LoginItem.setEnabled(newValue)
                        refreshLoginItem()
                    }
                ))
                .labelsHidden()
                .toggleStyle(.switch)
                .accessibilityLabel(SettingsCopy.openAtLogin)
            }
            if loginNeedsApproval {
                VStack(alignment: .leading, spacing: Theme.Space.xs) {
                    Text(SettingsCopy.loginItemOff).font(Theme.Font.caption).foregroundStyle(Theme.textSecondary)
                    Button(SettingsCopy.openLoginItems) { LoginItem.openSystemSettings() }
                        .buttonStyle(.rmLink)
                }
            }
            VStack(alignment: .leading, spacing: Theme.Space.xs) {
                HStack {
                    Text(SettingsCopy.openRemarkableAtStart).font(Theme.Font.body)
                    Spacer()
                    Toggle(SettingsCopy.openRemarkableAtStart, isOn: Binding(
                        get: { store.opensRemarkableAppAtStart },
                        set: { store.setOpensRemarkableAppAtStart($0) }
                    ))
                    .labelsHidden()
                    .toggleStyle(.switch)
                    .accessibilityLabel(SettingsCopy.openRemarkableAtStart)
                }
                Text(SettingsCopy.openRemarkableAtStartExplanation)
                    .font(Theme.Font.caption).foregroundStyle(Theme.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Account

    private var account: some View {
        section(SettingsCopy.accountHeading) {
            if let email = store.state?.auth.email, store.state?.auth.signedIn == true {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(SettingsCopy.signedInAs).font(Theme.Font.caption).foregroundStyle(Theme.textSecondary)
                        Text(email).font(Theme.Font.body).textSelection(.enabled)
                    }
                    .accessibilityElement(children: .combine)
                    Spacer()
                    if !confirmingSignOut {
                        Button(SettingsCopy.signOut) { confirmingSignOut = true }
                            .buttonStyle(.rmSecondary)
                    }
                }
                if confirmingSignOut {
                    VStack(alignment: .leading, spacing: Theme.Space.s) {
                        Text(SettingsCopy.signOutConfirmTitle).font(Theme.Font.bodyStrong)
                        Text(SettingsCopy.signOutConfirmBody)
                            .font(Theme.Font.caption).foregroundStyle(Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        HStack {
                            Button(SettingsCopy.signOutConfirmAction) {
                                confirmingSignOut = false
                                Task { await store.signOut() }
                            }
                            .buttonStyle(.rmSecondary)
                            Button(SettingsCopy.cancel) { confirmingSignOut = false }
                                .buttonStyle(.rmLink)
                        }
                    }
                    .padding(Theme.Space.m)
                    .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Theme.surfaceSunken))
                    .accessibilityElement(children: .contain)
                }
            } else {
                Text(SettingsCopy.notSignedIn).font(Theme.Font.body).foregroundStyle(Theme.textSecondary)
            }
        }
    }

    // MARK: Syncing

    private func syncing(_ settings: AppSettings) -> some View {
        section(SettingsCopy.syncingHeading) {
            DisclosureGroup(isExpanded: $showMore) {
                VStack(alignment: .leading, spacing: Theme.Space.m) {
                    VStack(alignment: .leading, spacing: Theme.Space.xs) {
                        HStack {
                            Toggle(SettingsCopy.limitPages, isOn: Binding(
                                get: { limitEnabled },
                                set: { on in
                                    limitEnabled = on
                                    limitError = false
                                    if on {
                                        if limitText.isEmpty { limitText = "100" }
                                        saveLimit()
                                    } else {
                                        Task { await store.updateSettings(SettingsUpdate(pageLimit: .some(nil))) }
                                    }
                                }
                            ))
                            .font(Theme.Font.body)
                            .toggleStyle(.switch)
                            Spacer()
                            if limitEnabled {
                                TextField(SettingsCopy.pageLimitField, text: $limitText)
                                    .textFieldStyle(.roundedBorder)
                                    .frame(width: 70)
                                    .multilineTextAlignment(.trailing)
                                    .accessibilityLabel(SettingsCopy.pageLimitField)
                                    .onSubmit { saveLimit() }
                                Button(SettingsCopy.save) { saveLimit() }
                                    .buttonStyle(.rmSecondary)
                            }
                        }
                        Text(SettingsCopy.limitPagesExplanation)
                            .font(Theme.Font.caption).foregroundStyle(Theme.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        if limitError {
                            Text(SettingsCopy.pageLimitInvalid).font(Theme.Font.caption).foregroundStyle(Theme.danger)
                        }
                    }
                    VStack(alignment: .leading, spacing: Theme.Space.xs) {
                        Text(SettingsCopy.folderLabel).font(Theme.Font.caption).foregroundStyle(Theme.textSecondary)
                        HStack(alignment: .top) {
                            Text(settings.sourceDirectory ?? SettingsCopy.folderNotSet)
                                .font(Theme.Font.caption)
                                .lineLimit(3)
                                .truncationMode(.middle)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Button(SettingsCopy.changeFolder) { chooseFolder() }
                                .buttonStyle(.rmSecondary)
                        }
                    }
                }
                .padding(.top, Theme.Space.s)
            } label: {
                Text(SettingsCopy.moreOptions).font(Theme.Font.bodyStrong)
            }
        }
    }

    // MARK: Developer options

    private func developer(_ settings: AppSettings) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            DisclosureGroup(isExpanded: $showDeveloper) {
                VStack(alignment: .leading, spacing: Theme.Space.s) {
                    Text(SettingsCopy.Developer.note).font(Theme.Font.caption).foregroundStyle(Theme.textSecondary)
                    Picker(SettingsCopy.Developer.server, selection: $server) {
                        Text(SettingsCopy.Developer.production).tag(ServerChoice.production)
                        Text(SettingsCopy.Developer.staging).tag(ServerChoice.staging)
                        Text(SettingsCopy.Developer.custom).tag(ServerChoice.custom)
                    }
                    .font(Theme.Font.caption)
                    .onChange(of: server) { _ in urlError = false; needsSignIn = false }
                    if server == .custom {
                        TextField(SettingsCopy.Developer.urlPlaceholder, text: $customURL)
                            .textFieldStyle(.roundedBorder)
                            .accessibilityLabel(SettingsCopy.Developer.urlLabel)
                            .onSubmit { applyServer(settings) }
                        if urlError {
                            Text(SettingsCopy.Developer.urlInvalid).font(Theme.Font.caption).foregroundStyle(Theme.danger)
                        }
                    }
                    HStack {
                        Button(SettingsCopy.Developer.apply) { applyServer(settings) }
                            .buttonStyle(.rmSecondary)
                            .disabled(!serverChanged(settings))
                        if needsSignIn {
                            Text(SettingsCopy.Developer.needsSignIn)
                                .font(Theme.Font.caption).foregroundStyle(Theme.warning)
                        }
                    }
                }
                .padding(.top, Theme.Space.s)
            } label: {
                Text(SettingsCopy.Developer.heading).font(Theme.Font.caption.weight(.medium))
                    .foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(.horizontal, Theme.Space.xs)
    }

    // MARK: Footer

    private var footer: some View {
        let shortVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
        let text = (shortVersion ?? store.state?.coreVersion).map(SettingsCopy.version)
        return Group {
            if let text { Text(text).font(Theme.Font.caption).foregroundStyle(Theme.textSecondary) }
        }
    }

    // MARK: Pieces

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.s) {
            Text(title).font(Theme.Font.label).foregroundStyle(Theme.textSecondary)
                .textCase(.uppercase)
                .accessibilityAddTraits(.isHeader)
            VStack(alignment: .leading, spacing: Theme.Space.m) { content() }
                .frame(maxWidth: .infinity, alignment: .leading)
                .rmCard(padding: Theme.Space.m)
        }
    }

    // MARK: Actions

    private func refreshLoginItem() {
        loginEnabled = LoginItem.isEnabled
        loginNeedsApproval = LoginItem.needsApprovalInSystemSettings
    }

    private func syncFields() {
        guard let settings = store.settings, settings != loadedFromSettings else { return }
        loadedFromSettings = settings
        if let limit = settings.pageLimit {
            limitEnabled = true
            limitText = String(limit)
        } else {
            limitEnabled = false
        }
        switch settings.environment.name {
        case .production: server = .production
        case .staging: server = .staging
        default:
            server = .custom
            customURL = settings.environment.apiURL
        }
    }

    private func saveLimit() {
        let trimmed = limitText.trimmingCharacters(in: .whitespaces)
        guard let value = Int(trimmed), SettingsCopy.pageLimitRange.contains(value) else {
            limitError = true
            return
        }
        limitError = false
        Task { await store.updateSettings(SettingsUpdate(pageLimit: .some(value))) }
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = SettingsCopy.chooseFolderPrompt
        panel.message = SettingsCopy.chooseFolderMessage
        guard panel.runModal() == .OK, let url = panel.url else { return }
        Task { await store.updateSettings(SettingsUpdate(sourceDirectory: url.path)) }
    }

    private func environmentSetting(_ settings: AppSettings) -> EnvironmentSetting? {
        switch server {
        case .production:
            return EnvironmentSetting(name: .production, apiURL: settings.environmentPresets["production"] ?? "")
        case .staging:
            return EnvironmentSetting(name: .staging, apiURL: settings.environmentPresets["staging"] ?? "")
        case .custom:
            let trimmed = customURL.trimmingCharacters(in: .whitespacesAndNewlines)
            return SettingsCopy.isValidServerURL(trimmed) ? EnvironmentSetting(name: .custom, apiURL: trimmed) : nil
        }
    }

    private func serverChanged(_ settings: AppSettings) -> Bool {
        switch server {
        case .production: return settings.environment.name != .production
        case .staging: return settings.environment.name != .staging
        case .custom:
            return settings.environment.name != .custom
                || settings.environment.apiURL != customURL.trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }

    private func applyServer(_ settings: AppSettings) {
        guard let setting = environmentSetting(settings) else { urlError = true; return }
        urlError = false
        Task {
            let signInNeeded = await store.updateSettings(SettingsUpdate(environment: setting))
            needsSignIn = signInNeeded
        }
    }
}
