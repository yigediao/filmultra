"use client";

import { createContext, type Dispatch, type ReactNode, type SetStateAction, useContext, useEffect, useState } from "react";

type AssetWorkspacePreferencesValue = {
  immersive: boolean;
  setImmersive: Dispatch<SetStateAction<boolean>>;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: Dispatch<SetStateAction<boolean>>;
  exifExpanded: boolean;
  setExifExpanded: Dispatch<SetStateAction<boolean>>;
};

const AssetWorkspacePreferencesContext = createContext<AssetWorkspacePreferencesValue | null>(null);

export function AssetWorkspacePreferencesProvider({ children }: { children: ReactNode }) {
  const [immersive, setImmersive] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [exifExpanded, setExifExpanded] = useState(false);

  useEffect(() => {
    document.body.dataset.assetImmersive = immersive ? "true" : "false";

    return () => {
      delete document.body.dataset.assetImmersive;
    };
  }, [immersive]);

  return (
    <AssetWorkspacePreferencesContext.Provider
      value={{
        immersive,
        setImmersive,
        sidebarCollapsed,
        setSidebarCollapsed,
        exifExpanded,
        setExifExpanded,
      }}
    >
      {children}
    </AssetWorkspacePreferencesContext.Provider>
  );
}

export function useAssetWorkspacePreferences() {
  const context = useContext(AssetWorkspacePreferencesContext);

  if (!context) {
    throw new Error("useAssetWorkspacePreferences must be used within AssetWorkspacePreferencesProvider");
  }

  return context;
}
