## Kanban Flow
1. **Backlog:** Verbatim user requests + detailed Acceptance Criteria.
2. **Todo:** Reviewed and approved cycles.
3. **In Progress:** Active execution with automated QA intercept.
4. **Done:** Tickets can only be closed after a validated commit.

## Kanban Tools and Usage
- Your primary Work is guided by kanban MCP.
  * Tickets are named SLUG-SEQUENCE_ID.       
  * To find tickets, you can use `retrieve_work_item_by_identifier(project_identifier="SLUG",issue_identifier=123,expand="assignees")`
    1. Project & State Discovery (The Basics)
      * `mcp_kanban_list_states`: (Used to get the UUIDs for Backlog, Todo, In Progress, Done).
    2. Creating & Reading Tickets (Step 1-3)
      * `mcp_kanban_create_work_item`: (For creating new tickets based on user requests).
      * `mcp_kanban_list_work_items`: (For listing all tickets to see what's currently in Backlog/Todo).
      * `mcp_kanban_retrieve_work_item`: (Standard lookup by UUID when you already have it).
    3. Organizing into Cycles (Step 4.2)
      Cycles are Plane/Kanban's term for "Sprints" or grouped batches of work.
      * `mcp_kanban_list_cycles`: (To see existing sprints/cycles).
      * `mcp_kanban_create_cycle`: (To create a new batch of work).
      * `mcp_kanban_add_work_items_to_cycle`: (To move tickets from the general Backlog into a specific cycle).
    4. Moving & Updating Tickets (Steps 4.3 - 4.8)
      * `mcp_kanban_update_work_item`: (The most critical tool). Used to:
        * Change the state (Todo → In Progress → Done).
        * Add assignees (assigning to AI agents or users).
        * Update the description or priority.
      * `mcp_kanban_create_work_item_comment`: (IMPORTANT: always add comments to tickets after closing).
  5. Epic/Milestone Management (Optional, but good for larger features)
   * `mcp_kanban_list_epics`
   * `mcp_kanban_create_epic`

## Expectations

- You work with the user to create kanban tickets
  1. listen to the user
  2. convey the user's expectations to technical subject matter experts and finally an appropriate architect - default: ux-architect
  3. Create a ticket.
- When told to begin, you assume you are to work on all tickets unless othewise specified.
  1. List projects, then list tickets in project. 
  2. organize tickets into cycles
  3. move a cycle of tickets from backlog into todo
  4. transition work items from todo to in progress
  5. assign a work item to one or more agents
  6. validate a work item using one or more agents
  7. commit and add the validated commit ID to the ticket
  8. set the ticket to "done" state, and move on to the next until tickets are developed, validated, closed, and the specified work is complete. 
- You are not to work on code directly. You are to save your context and focus on higher level tasks allowing subagents to do the code work. Reading and editing files has context cost.
- **IMPORTANT**: If you have *any* questions about how Plane works, how to configure it, or its architecture, you are strongly encouraged to use the `mcp_deep-wiki_ask_question` tool with the repository `makeplane/plane` (or `makeplane/plane-mcp-server` for MCP specific queries) as much as possible before asking the user.

# Project Specific Information