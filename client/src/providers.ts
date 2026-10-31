// Retrieval providers: where column j of R is stored. The class fixes the provider's name and host; the
// configuration only supplies its parameters (a site name, a file ID), so the name shown to users always matches
// the host that is contacted. See providers/*.md for the assessments.

import { RcPirError } from "./errors.js";
import type { Params } from "./params.js";
import { columnLocation } from "./query.js";

export interface RetrievalProvider {
  /** Display name, fixed by the class. */
  readonly name: string;
  /** URL and byte offset of column j (L bytes). */
  locate(j: number, params: Params): { url: URL; offset: number };
}

/** The shards of R on https://<site>.github.io/rc-pir/r/<k> (docs/protocol.md §2). */
export class GitHubPages implements RetrievalProvider {
  readonly name = "GitHub Pages";
  private readonly origin: URL;

  constructor(site: string) {
    if (!/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/i.test(site)) {
      throw new RcPirError("bad-argument", `not a GitHub Pages site name: ${site}`);
    }
    this.origin = new URL(`https://${site.toLowerCase()}.github.io`);
  }

  locate(j: number, p: Params): { url: URL; offset: number } {
    const { path, offset } = columnLocation(j, p.columns_per_shard, p.L);
    return { url: new URL(path, this.origin), offset };
  }
}

/**
 * All of R in one Google Drive file shared as "anyone with the link" (column j at offset j * L), read through the
 * Drive API with an API key: the only Drive endpoint browsers can use from another site (providers/GOOGLE_DRIVE.md).
 */
export class GoogleDrive implements RetrievalProvider {
  readonly name = "Google Drive";
  private readonly url: URL;

  constructor(fileId: string, apiKey: string) {
    if (!/^[A-Za-z0-9_-]+$/.test(fileId)) throw new RcPirError("bad-argument", `not a Google Drive file ID: ${fileId}`);
    if (!apiKey) throw new RcPirError("bad-argument", "Google Drive needs an API key");
    this.url = new URL(`https://www.googleapis.com/drive/v3/files/${fileId}`);
    this.url.searchParams.set("alt", "media");
    this.url.searchParams.set("key", apiKey);
  }

  locate(j: number, p: Params): { url: URL; offset: number } {
    return { url: this.url, offset: j * p.L };
  }
}
