/**
 * OpenCode plugin entry point.
 *
 * CANNBot's current bundle is content-oriented: its useful behavior is provided
 * by the skills and agents installed by the CLI. Exporting a valid plugin hook
 * makes that bundle a first-class OpenCode npm plugin without adding side
 * effects of its own.
 */
export const CANNBotPlugin = async () => ({});

export default {
  id: "cannbot",
  server: CANNBotPlugin,
  setup: async () => {},
};
