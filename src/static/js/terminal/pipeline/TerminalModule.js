/**
 * Base class for all Terminal modules in the Pipeline.
 * Modules should extend this class and override the necessary methods.
 */
export class TerminalModule {
  constructor(name = "UnknownModule", priority = 0) {
    this.name = name;
    this.priority = priority;
  }

  /**
   * Called when the module is registered with the pipeline.
   * @param {Object} terminal - The xterm.js instance
   * @param {Object} tab - The tab object holding session state
   */
  setup(terminal, tab) {}

  /**
   * Called to clean up resources when the module is removed or terminal is destroyed.
   */
  dispose() {}

  /**
   * Determines if this module should process the given input event.
   * @param {Event} event - The normalized DOM or custom event
   * @param {Object} context - The TerminalContext object exposing state and api
   * @returns {boolean} True if this module wants to handle the event.
   */
  inputNeedsProcess(event, context) {
    return false;
  }

  /**
   * Processes the input event.
   * @param {Event} event - The normalized DOM or custom event
   * @param {Object} context - The TerminalContext object exposing state and api
   * @returns {boolean} True if the event was consumed (stops pipeline propagation).
   */
  processInput(event, context) {
    return false;
  }

  /**
   * Determines if this module should process the given output data.
   * @param {string} data - The data string coming from the PTY
   * @param {Object} context - The TerminalContext object exposing state and api
   * @returns {boolean} True if this module wants to handle the output data.
   */
  outputNeedsProcess(data, context) {
    return false;
  }

  /**
   * Processes the output data.
   * @param {string} data - The data string coming from the PTY
   * @param {Object} context - The TerminalContext object exposing state and api
   * @returns {string} The modified data string (or original data if no changes).
   */
  processOutput(data, context) {
    return data;
  }
}
