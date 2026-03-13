"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { href: "/", label: "图库" },
  { href: "/people", label: "人物" },
  { href: "/people/review", label: "待确认" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function MobileTabBar() {
  const pathname = usePathname();

  return (
    <nav className="mobile-tab-bar" aria-label="主导航">
      {tabs.map((tab) => (
        <Link
          key={tab.href}
          href={tab.href}
          className={`mobile-tab-link ${isActive(pathname, tab.href) ? "active" : ""}`}
        >
          <span>{tab.label}</span>
        </Link>
      ))}
    </nav>
  );
}
