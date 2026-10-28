# Adding OBD-II later (prepared, not active)

OBD-II is the diagnostic port under the dash on every US car since 1996. An adapter
plugs in and lets software read trouble codes and live sensor data (RPM, coolant temp,
fuel trims, misfire counts). It sees only what the car's computers monitor: a 2010
manual Accent has no transmission computer, so OBD can't see a shifting or clutch fault.

## When the user asks to turn it on

1. **Adapter.** The user chooses and buys it. Roundups favor OBDLink MX+ (~$100, Bluetooth,
   own chip) or OBDLink EX (USB, Windows-friendly, no pairing). Cheap ELM327 clones drop
   data. A USB adapter avoids Windows Bluetooth COM-port pairing trouble.
2. **Software.** Start with the read-only MCP server
   https://github.com/iamneilroberts/shadetree-ai (Claude reads codes, freeze frame,
   live data; built on python-OBD). Alternative: https://github.com/speed785/open-mechanic.
   Neither was tested here. Before installing: read the repo, check Windows support, run
   it against the adapter with the engine running, and confirm one known value
   (coolant temp vs the dash gauge) as the positive control.
3. **Read-only first.** Don't use any command that clears codes or writes to a module
   until the user asks; clearing codes erases freeze-frame evidence.
4. **Where data goes.** Each session's codes and a short summary go in the vehicle note
   under `## Observations` (source `scan`) (date, mileage, codes with their freeze frame, notable live values).
   Raw logs (CSV) go in an `obd/` folder beside the vehicle's other files.
5. **How it feeds diagnosis.** Codes become evidence in step 4 of the workflow, the same
   as owner reports: look up each code in the factory manual's DTC section
   (`carkit find ... "DTC|P0..."`), never from memory.
