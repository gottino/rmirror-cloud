import { getLatestAgentVersion, type AgentVersionInfo } from './api';

/** Shown when no download URL can be found. There is no stable "latest" DMG to fall back to. */
export const DOWNLOAD_UNAVAILABLE_MESSAGE = 'Download is temporarily unavailable, try again in a minute.';

/**
 * The Mac app's download URL: from the version info already loaded, otherwise
 * asked from the server once more. Returns null when the server cannot say,
 * so callers show DOWNLOAD_UNAVAILABLE_MESSAGE instead of a stale version.
 */
export async function resolveAgentDownloadUrl(known?: AgentVersionInfo | null): Promise<string | null> {
  const url = known?.platforms.macos?.url;
  if (url) return url;
  try {
    const info = await getLatestAgentVersion();
    return info.platforms.macos?.url ?? null;
  } catch {
    return null;
  }
}
