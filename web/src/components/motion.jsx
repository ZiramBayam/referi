"use client";

import { motion, useReducedMotion } from "motion/react";

export const EASE = [0.16, 1, 0.3, 1];

/**
 * Masuk saat digulir yang MENAMBAH nilai pada blok yang tata letaknya sudah jadi
 * (naik + fade halus, sekali saja). Dengan `prefers-reduced-motion` isinya dirender
 * statis, bukan disembunyikan.
 *
 * @param {{ children: any, delay?: number, y?: number, className?: string,
 *   as?: "div" | "section" | "li" | "span" | "tr", key?: any }} props
 */
export function Reveal({ children, delay = 0, y = 18, className, as = "div" }) {
  const reduce = useReducedMotion();
  const MotionTag = motion[as];
  if (reduce) {
    const Tag = as;
    return <Tag className={className}>{children}</Tag>;
  }
  return (
    <MotionTag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -12% 0px" }}
      transition={{ duration: 0.6, ease: EASE, delay }}
    >
      {children}
    </MotionTag>
  );
}

/**
 * Anak-anaknya naik berurutan saat grupnya masuk viewport.
 * @param {{ children: any[], step?: number, className?: string }} props
 */
export function RevealStagger({ children, step = 0.08, className }) {
  return (
    <div className={className}>
      {children.map((child, i) => (
        <Reveal key={i} delay={i * step}>
          {child}
        </Reveal>
      ))}
    </div>
  );
}
