// OpenReflex plugin for OpenCode.
// Forwards lifecycle events to `openreflex hook opencode <event>` (JSON on stdin) and feeds the returned
// Execution Context / alerts back to the model. Capture failures never interrupt the session.
import type { Plugin } from "@opencode-ai/plugin"

type HookResult = { context?: string | null; notice?: string | null }

export const OpenReflex: Plugin = async ({ directory }) => {
  const bin = process.env.OPENREFLEX_BIN ?? "openreflex"
  // sessionID -> Execution Context for the current turn, appended to the system prompt.
  const pending = new Map<string, string>()

  async function send(event: string, body: Record<string, unknown>): Promise<HookResult> {
    try {
      const proc = Bun.spawn([bin, "hook", "opencode", event], {
        cwd: directory, stdin: "pipe", stdout: "pipe", stderr: "ignore",
      })
      proc.stdin.write(JSON.stringify({ event, cwd: directory, ...body }))
      proc.stdin.end()
      const timer = setTimeout(() => proc.kill(), 10_000)
      const text = await new Response(proc.stdout).text()
      clearTimeout(timer)
      return text.trim() ? (JSON.parse(text) as HookResult) : {}
    } catch {
      return {}
    }
  }

  return {
    "chat.message": async (input, output) => {
      const prompt = output.parts
        .filter((part: any) => part.type === "text" && !part.synthetic)
        .map((part: any) => part.text)
        .join("\n")
      if (!prompt) return
      const result = await send("chat.message", { session_id: input.sessionID, prompt })
      if (result.context) pending.set(input.sessionID, result.context)
    },

    "experimental.chat.system.transform": async (input, output) => {
      const context = input.sessionID ? pending.get(input.sessionID) : undefined
      if (context) output.system.push(context)
    },

    "tool.execute.before": async (input, output) => {
      await send("tool.before", { session_id: input.sessionID, tool: input.tool, call_id: input.callID, args: output.args })
    },

    "tool.execute.after": async (input, output) => {
      const result = await send("tool.after", {
        session_id: input.sessionID, tool: input.tool, call_id: input.callID, args: input.args,
        output_chars: typeof output.output === "string" ? output.output.length : 0,
      })
      if (result.context) output.output = `${output.output ?? ""}\n\n${result.context}`
    },

    // tool.execute.after only runs for successful tools; failures arrive as tool part updates.
    event: async ({ event }: { event: any }) => {
      const props = event.properties ?? {}
      const part = props.part
      if (event.type === "message.part.updated" && part?.type === "tool" && part.state?.status === "error") {
        await send("tool.error", {
          session_id: part.sessionID, tool: part.tool, call_id: part.callID, args: part.state.input, error: part.state.error,
        })
      } else if (event.type === "session.idle" || (event.type === "session.status" && props.status?.type === "idle")) {
        pending.delete(props.sessionID)
        await send("session.idle", { session_id: props.sessionID })
      } else if (event.type === "session.compacted") {
        await send("session.compacted", { session_id: props.sessionID })
      } else if (event.type === "session.deleted") {
        await send("session.deleted", { session_id: props.info?.id })
      }
    },
  }
}
