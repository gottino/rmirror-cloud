import RMirrorKit
import SwiftUI

// PLACEHOLDERS. The onboarding implementation replaces this whole file.
struct StartingView: View { var body: some View { ProgressView() } }
struct CoreProblemView: View { let failure: CoreFailure; var body: some View { Text("Core problem") } }
struct SignInView: View { let reason: Stage.SignInReason; var body: some View { Text("Sign in") } }
struct RemarkableMissingView: View { var body: some View { Text("reMarkable app missing") } }
struct PermissionView: View { var body: some View { Text("Permission") } }
struct FirstSyncView: View { var body: some View { Text("First sync") } }
struct FirstSyncProgressView: View { var body: some View { Text("Progress") } }
struct FirstSyncResultView: View { var body: some View { Text("Result") } }
