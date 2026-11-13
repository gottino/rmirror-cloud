'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Hold an object URL for a Blob. The previous URL is revoked when a new blob
 * replaces it, and the current one is revoked on unmount. A blob set after
 * unmount (e.g. a fetch that finished late) never gets a URL.
 */
export function useObjectUrl(): [string | null, (blob: Blob | null) => void] {
  const [url, setUrl] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    };
  }, []);

  const setBlob = useCallback((blob: Blob | null) => {
    if (!mounted.current) return;
    const next = blob ? URL.createObjectURL(blob) : null;
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = next;
    setUrl(next);
  }, []);

  return [url, setBlob];
}
