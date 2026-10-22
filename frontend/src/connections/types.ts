export type Connection = {
  id: string;
  provider: "google_drive";
  name: string;
  status: "connected" | "reconnect_required" | "disconnected";
  created_at: string;
  checked_at: string;
};
export type ConnectionsCatalog = {
  provider: "pipedream";
  configured: boolean;
  environment: "development" | "production";
  setup: string;
  connections: Connection[];
  capabilities: string[];
  activity: {
    connection_id: string | null;
    operation: string;
    status: string;
    created_at: string;
  }[];
};
export type DriveFile = {
  id: string;
  name: string;
  mime_type: string;
  url: string;
  modified_at: string | null;
  readable: boolean;
};
export type DriveDocument = { file: DriveFile; text: string; truncated: boolean };
export type DriveSource = { connection_id: string; file_ids: string[] };
