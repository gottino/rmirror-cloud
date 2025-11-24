/**
 * API client for rMirror backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';

export interface Notebook {
  id: number;
  name: string;
  uuid: string;
  created_at: string;
  updated_at: string;
  page_count: number;
}

export interface Page {
  id: number;
  notebook_id: number;
  page_number: number;
  ocr_status: string;
  ocr_text: string | null;
  ocr_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotebookWithPages extends Notebook {
  pages: Page[];
}

/**
 * Fetch notebooks for the current user
 */
export async function getNotebooks(token: string): Promise<Notebook[]> {
  const response = await fetch(`${API_URL}/notebooks`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch notebooks');
  }

  return response.json();
}

/**
 * Fetch a single notebook with its pages
 */
export async function getNotebook(id: number, token: string): Promise<NotebookWithPages> {
  const response = await fetch(`${API_URL}/notebooks/${id}`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch notebook');
  }

  return response.json();
}
