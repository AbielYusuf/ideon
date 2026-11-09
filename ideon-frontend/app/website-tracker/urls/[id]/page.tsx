import { Suspense } from "react";

import { LoadingBlock } from "../../ui";
import { UrlDetailClient } from "./url-detail-client";

export default function UrlDetailPage() {
  return (
    <Suspense fallback={<LoadingBlock label="Loading URL history…" />}>
      <UrlDetailClient />
    </Suspense>
  );
}
