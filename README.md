# Linux Ultimate Ears

Research and implementation project for controlling Ultimate Ears speakers on
Linux. The first phase maps the Android app's Bluetooth control logic; interface
design follows that work.

The connected phone's BOOM app (`com.logitech.ueboom` 7.22.0.355) was extracted and
inspected locally using REA 6.5.0 and JADX headless MCP 0.7.1. The research found
separate legacy and CPP protocol families, Bluetooth Classic serial control,
and BLE discovery/wake behavior. Compatibility depends on hardware identifiers,
features and firmware, including variants sold under the same retail name.

- [Protocol and architecture findings](docs/protocol-research.md)
- [Reproduce the research](docs/research-workflow.md)
- [Legacy command IDs](docs/legacy-command-catalog.json)
- [Evidence index](docs/evidence-index.json)
- [Interface direction](docs/interface-direction.md)
- [Official speaker images and colours](assets/speakers/README.md)

This repository currently contains research and reproducible analysis helpers.
There is no runnable Linux controller or interface yet. Findings are static;
end-to-end speaker behavior still needs hardware validation.

APKs, vendor decompilation, raw device evidence and downloaded tools are kept in
ignored `.local/` and are not published in this repository.
