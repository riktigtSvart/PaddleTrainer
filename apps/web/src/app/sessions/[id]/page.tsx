import SessionWorkspace from "@/components/session-analysis/workspace";
import "@/styles/session-analysis.css";

export default async function SessionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SessionWorkspace key={id} sessionId={id} />;
}
