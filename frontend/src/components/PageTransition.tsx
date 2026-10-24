import { AnimatePresence, motion } from "framer-motion";
import { useLocation, useOutlet } from "react-router-dom";

/** Wraps the routed page in a brief fade + rise, keyed by pathname so
 * AnimatePresence treats every navigation as a real enter/exit instead of a
 * silent swap. Kept deliberately subtle (200ms, 8px) — this runs on every
 * single navigation in the app, so anything showier would get tiring fast. */
export default function PageTransition() {
  const location = useLocation();
  const outlet = useOutlet();

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
      >
        {outlet}
      </motion.div>
    </AnimatePresence>
  );
}
