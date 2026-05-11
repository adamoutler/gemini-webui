import { CopyPlugin } from "./CopyPlugin.js";
import { PastePlugin } from "./PastePlugin.js";
import { ContextMenuPlugin } from "./ContextMenuPlugin.js";
import { HotkeyPlugin } from "./HotkeyPlugin.js";

export function registerDefaultPlugins(pipeline) {
  pipeline.registerModule(new CopyPlugin());
  pipeline.registerModule(new PastePlugin());
  pipeline.registerModule(new ContextMenuPlugin());
  pipeline.registerModule(new HotkeyPlugin());
}
