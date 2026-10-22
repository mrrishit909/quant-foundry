// Fonts load only in the standalone site; an embedding host keeps its own font policy and the
// stylesheet falls back to system serif and condensed sans stacks.
import "@fontsource-variable/fraunces/opsz.css";
import "@fontsource-variable/fraunces/opsz-italic.css";
import "@fontsource/ibm-plex-sans-condensed/400.css";
import "@fontsource/ibm-plex-sans-condensed/500.css";
import "@fontsource/ibm-plex-sans-condensed/600.css";
import { mount } from "./index";
import { loadKinetic } from "./lib/useKinetic";

void loadKinetic(); // fetch the motion chunk alongside the data snapshot

const el = document.getElementById("app");
if (el) {
  el.removeAttribute("data-boot");
  mount(el, { basePath: import.meta.env.BASE_URL });
}
