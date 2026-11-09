import type { Metadata } from "next";

import IdeaDetail from "./idea-detail";

export const metadata: Metadata = {
  title: "Idea detail | Ideon",
};

export const instant = false;

export default async function IdeaDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return <IdeaDetail key={id} ideaId={id} />;
}
