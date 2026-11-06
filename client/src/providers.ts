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
  /** At most this many column requests in flight (hosts that reject more); default: all s at once. */
  readonly maxParallel?: number;
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

/**
 * All of R in one OneDrive file (column j at offset j * L), from its "Anyone with the link" share link
 * https://<tenant>-my.sharepoint.com/:<type>:/<g|r>/personal/<user>/<token>. Read through
 * /personal/<user>/_layouts/15/download.aspx?share=<token>: no cookie, Access-Control-Allow-Origin: *, the only
 * OneDrive endpoint browsers can use from another site. Folder links do not work there (providers/ONEDRIVE.md).
 */
export class OneDrive implements RetrievalProvider {
  readonly name = "OneDrive";
  private readonly url: URL;

  constructor(shareLink: string) {
    const bad = (why: string) => new RcPirError("bad-argument", `not a OneDrive file share link (${why}): ${shareLink}`);
    let link: URL;
    try {
      link = new URL(shareLink);
    } catch {
      throw bad("invalid URL");
    }
    if (link.protocol !== "https:" || link.port || !/^[a-z0-9-]+-my\.sharepoint\.com$/.test(link.hostname)) {
      throw bad("expected https://<tenant>-my.sharepoint.com");
    }
    const m = /^\/:([a-z]):\/[gr]\/personal\/([A-Za-z0-9_]+)\/([A-Za-z0-9_-]+)\/?$/.exec(link.pathname);
    if (!m) throw bad("expected /:<type>:/g/personal/<user>/<token>");
    if (m[1] === "f") throw bad("this is a folder link; share the file itself");
    this.url = new URL(`https://${link.hostname}/personal/${m[2]}/_layouts/15/download.aspx`);
    this.url.searchParams.set("share", m[3]!);
  }

  locate(j: number, p: Params): { url: URL; offset: number } {
    return { url: this.url, offset: j * p.L };
  }
}

/**
 * All of R in one Dropbox file (column j at offset j * L), from its shared link
 * https://www.dropbox.com/scl/fi/<id>/<name>?rlkey=<key>, or in several copies of that file (one link each). Read from
 * the same path on dl.dropboxusercontent.com: no redirect and Access-Control-Allow-Origin: * (the www.dropbox.com link
 * redirects, without CORS on the first hop, to temporary URLs). Dropbox answers 429 (without CORS headers) above
 * roughly 40 requests per second per file, with bursts of ~50; 24 in flight per copy keeps each file at ~30 per
 * second. Column j is read from copy j mod n: independent of the block read, like S (providers/DROPBOX.md).
 */
export class Dropbox implements RetrievalProvider {
  readonly name = "Dropbox";
  readonly maxParallel: number;
  private readonly urls: URL[];

  /** `sharedLinks`: one link, or links to identical copies of the file (all of them must hold the same R). */
  constructor(sharedLinks: string | readonly string[]) {
    const links = typeof sharedLinks === "string" ? [sharedLinks] : [...sharedLinks];
    if (!links.length) throw new RcPirError("bad-argument", "Dropbox needs at least one shared link");
    this.urls = links.map((l) => Dropbox.directUrl(l));
    this.maxParallel = 24 * this.urls.length;
  }

  locate(j: number, p: Params): { url: URL; offset: number } {
    return { url: this.urls[j % this.urls.length]!, offset: j * p.L };
  }

  private static directUrl(sharedLink: string): URL {
    const bad = (why: string) => new RcPirError("bad-argument", `not a Dropbox shared file link (${why}): ${sharedLink}`);
    let link: URL;
    try {
      link = new URL(sharedLink);
    } catch {
      throw bad("invalid URL");
    }
    if (link.protocol !== "https:" || link.port || !["www.dropbox.com", "dropbox.com", "dl.dropboxusercontent.com"].includes(link.hostname)) {
      throw bad("expected https://www.dropbox.com");
    }
    const m = /^\/scl\/fi\/([a-z0-9]+)\/([A-Za-z0-9._~%-]+)$/i.exec(link.pathname);
    if (!m) throw bad("expected /scl/fi/<id>/<name>");
    const rlkey = link.searchParams.get("rlkey");
    if (!rlkey || !/^[a-z0-9]+$/i.test(rlkey)) throw bad("missing rlkey");
    const url = new URL(`https://dl.dropboxusercontent.com/scl/fi/${m[1]}/${m[2]}`);
    url.searchParams.set("rlkey", rlkey);
    return url;
  }
}
