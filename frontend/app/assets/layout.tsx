import type { ReactNode } from "react";

import { AssetWorkspacePreferencesProvider } from "@/components/asset-workspace-preferences";

export default function AssetsLayout({ children }: { children: ReactNode }) {
  return <AssetWorkspacePreferencesProvider>{children}</AssetWorkspacePreferencesProvider>;
}
