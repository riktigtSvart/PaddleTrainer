import { forwardGoals } from "@/lib/planning-goals/proxy";

type Context = { params: Promise<{ path: string[] }> };
async function forward(request: Request, context: Context) {
  const { path } = await context.params;
  return forwardGoals(
    request,
    path,
    process.env.PADDLETRAINER_API_URL ??
      process.env.NEXT_PUBLIC_API_URL ??
      "http://127.0.0.1:8000",
  );
}
export const GET = forward;
export const POST = forward;
