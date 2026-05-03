import { requireAuth, AuthError } from "@/lib/auth-bridge";
import { prisma } from "@/lib/prisma";
import { NextRequest, NextResponse } from "next/server";
import * as fs from "fs/promises";
import * as path from "path";

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  let userId: string;
  try {
    ({ userId } = await requireAuth());
  } catch (e) {
    if (e instanceof AuthError) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    throw e;
  }

  const { id } = await params;
  const engagement = await prisma.engagement.findFirst({
    where: { id, userId },
  });

  if (!engagement) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Try to read opplan from workspace
  const WORKSPACE = process.env.WORKSPACE_PATH ?? path.join(process.env.HOME ?? "", ".decepticon", "workspace");
  const wsPath = path.join(WORKSPACE, engagement.name);
  const opplanPath = path.join(wsPath, "plan", "opplan.json");

  try {
    const stat = await fs.stat(opplanPath);
    const content = await fs.readFile(opplanPath, "utf-8");
    const data = JSON.parse(content);

    // Downgrade stale IN_PROGRESS objectives: if the file hasn't been
    // touched in 10 minutes, any objective still marked in-progress was
    // abandoned by a crashed loop. Show it as pending so the UI doesn't
    // lie about it "Running".
    const STALE_THRESHOLD_MS = 10 * 60 * 1000;
    if (Date.now() - stat.mtimeMs > STALE_THRESHOLD_MS) {
      const stale: string[] = [];
      for (const obj of data.objectives ?? []) {
        if (obj.status === "in-progress") {
          obj.status = "pending";
          stale.push(obj.id);
        }
      }
      if (stale.length > 0) {
        console.log(
          `[opplan API] Downgraded stale objectives: ${stale.join(", ")} ` +
          `(file untouched for ${Math.round((Date.now() - stat.mtimeMs) / 1000)}s)`
        );
      }
    }

    return NextResponse.json(data);
  } catch {
    // File not found or invalid — return empty
  }

  return NextResponse.json({ objectives: [] });
}
