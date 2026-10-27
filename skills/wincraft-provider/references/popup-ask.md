# Popup-Ask as a WinCraft provider

This reference describes an optional transport for the installed `popup-ask`
structured-question skill. The skill remains the authority for question validation,
`Other` injection, preview rules, and result serialization. WinCraft supplies a
temporary native world and routes typed user actions back to the provider.

## Run

1. Create the usual structured request as a UTF-8 JSON file. Use the skill's `--file`
   channel rather than embedding Chinese JSON in a shell command.
2. Obtain the actual runtime descriptor from the running host's manager or startup
   output. Pass the installed `popup_ask.py` path explicitly; the provider does not
   scan user profiles, guess a runtime port, or print the descriptor.
3. Run:

   ```powershell
   python examples/python/popup_ask_provider.py `
     --runtime "<actual runtime descriptor path>" `
     --popup-ask-script "<installed popup_ask.py path>" `
     --request-file "<UTF-8 structured request path>"
   ```

   Add `--json` when a tool needs the skill's existing structured JSON result instead
   of its default stable text summary. The default wait is 30 minutes and can be
   changed with `--timeout-seconds` (1–86400).

The provider imports the explicitly selected skill script, calls its existing
`load_structured_payload` / `build_validated_payload` path, then delegates success and
cancellation serialization to the same module. Its options and notes exist only in
this provider process and the world's rebuildable scene. No answer is written to an
external business system.

## User interaction and boundaries

- One temporary world contains the request and all questions. Options are typed buttons;
  single- and multi-select state is provider-owned. Selected-option previews are
  rendered as ordinary `text` components.
- Each question has a multiline `textarea`. Tab from the chosen option moves directly
  to its notes field. The current renderer allows up to 8192 UTF-16 code units per
  question and shows the count. Click **Save notes** to keep editing, or press Ctrl+Enter
  in the notes field to submit the answer with that draft. Selecting `Other` requires
  non-empty notes.
- **Submit answers** follows the existing unanswered-question confirmation behavior.
  No business action occurs while the user is choosing.
- **Cancel** returns `cancel_button`; Escape uses a separate `shortcut_action` and returns
  `escape_key`; closing the native window returns `window_closed`.
- Confirmed success and user cancellation keep the installed skill's normal exit status.
  Timeout, connection/acknowledgement uncertainty, and a busy single-slot response emit
  an error payload and a non-zero process exit; they are never translated into an answer.
- After a successful submission, the provider saves only the observed native `x/y`
  position and width/height to a local preference file under the current user's local
  app-data directory. The next popup starts there but remains human-movable. Use
  `--no-remember-position` to disable this, or remove that preference file to reset it.
  No question text, answer, token, or runtime descriptor is stored there.
- The whole-question wait is independent of the ordinary 10-second component action
  acknowledgement. A host/connection failure before the final result is confirmed
  returns an error with an unknown outcome. The adapter never retries the answer.
- Host capabilities must advertise `textarea`, `keyboard_shortcuts: ["escape", "ctrl_enter"]`,
  and `button_features: ["selection_groups"]`.
  An older host fails before the adapter creates a world; it does not silently pretend
  those controls work.
- The transport reserves one Popup-Ask slot per Windows interactive session before it
  connects to the host or creates a world. A concurrent invocation returns a localized
  busy error, creates no second window, and directs the caller to the WinCraft World
  Manager. It never steals focus from the existing request. Windows uses a local named
  mutex; other platforms use an advisory lock file. Both are released on normal
  completion, cancellation, disconnect, and process termination.

This is an explicitly invoked adapter example. It does not replace or modify the
installed skill's default Tk transport. Unit and cross-process tests cover the quota;
the visible manager entry, native positioning, keyboard/IME flow, and title focus still
require Tauri release and Windows UI acceptance. Browser DOM checks do not prove them.
