/*
 * SAC Theme Preferences console tools
 *
 * Usage:
 *   1. Open the Theme Preferences dialog in an SAC story.
 *   2. Paste this entire file into Chrome DevTools Console and press Enter.
 *   3. Export:
 *        await SACThemeTools.exportJSON();
 *      Import an edited file without saving the dialog:
 *        await SACThemeTools.applyFromFile();
 *      Import all optional setting groups and invoke Save:
 *        await SACThemeTools.applyFromFile({
 *          applyStorySettings: true,
 *          applyWidgetSettings: true,
 *          applySectionSettings: true,
 *          save: true
 *        });
 *
 * This utility uses private SAC/UI5 implementation details. Re-test it after an
 * SAC tenant upgrade because SAP does not publish these objects as a stable API.
 */

(() => {
  "use strict";

  const TOOL_VERSION = "1.1.2";
  const FORMAT = "sac-theme-preferences";
  const SCHEMA_VERSION = 1;
  const DIALOG_CLASS =
    "sap.fpa.ui.appBuilding.theming.ui.Story2PreferencesDialog";
  const COLOR_PROVIDER_ID = "sap.fpa.appBuilding.theme.color";
  const PALETTE_PROVIDER_ID = "sap.fpa.appBuilding.theme.palette";
  const STORY_ROOT_ID = "sap.fpa.appBuilding.theme.application";
  const WIDGET_ROOT_ID = "sap.fpa.appBuilding.theme.widget";
  const SECTION_ROOT_ID = "sap.fpa.story.theme.repeatablegroup";

  const clone = (value) => JSON.parse(JSON.stringify(value));
  const wait = (milliseconds) =>
    new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  function getRegistryElements() {
    const registry = window.sap?.ui?.core?.Element?.registry;
    if (typeof registry?.all === "function") {
      return Object.values(registry.all());
    }

    const core = window.sap?.ui?.getCore?.();
    return Object.values(core?.mElements || {});
  }

  function getDialog() {
    if (!window.sap?.ui) {
      throw new Error("SAPUI5 was not found on this page.");
    }

    const dialog = getRegistryElements().find(
      (element) =>
        element?.getMetadata?.().getName?.() === DIALOG_CLASS &&
        element?.isOpen?.()
    );

    if (!dialog?._aStoryPrefs || !dialog?._oDataProvider?._aProviders) {
      throw new Error(
        "Open Theme Preferences in the SAC story editor, then run the command again."
      );
    }

    return dialog;
  }

  function getProvider(dialog, id) {
    const provider = dialog._oDataProvider._aProviders.find(
      (candidate) => candidate.getId?.() === id
    );

    if (!provider) {
      throw new Error(`SAC theme provider not found: ${id}`);
    }

    return provider;
  }

  function getPreference(dialog, id) {
    const preference = dialog._aStoryPrefs.find((entry) => entry.id === id);
    if (!preference) {
      throw new Error(`SAC theme preference not found: ${id}`);
    }
    return preference;
  }

  function buildProviderIndex(dialog) {
    return new Map(
      dialog._oDataProvider._aProviders.map((provider) => [
        provider.getId?.(),
        {
          id: provider.getId?.(),
          parentId: provider.getParentId?.() || null,
          description: provider.getDescription?.() || "",
        },
      ])
    );
  }

  function hasAncestor(providerIndex, id, ancestorId) {
    const seen = new Set();
    let currentId = id;

    while (currentId && !seen.has(currentId)) {
      if (currentId === ancestorId) return true;
      seen.add(currentId);
      currentId = providerIndex.get(currentId)?.parentId;
    }

    return false;
  }

  function buildExport(dialog, options) {
    const providerIndex = buildProviderIndex(dialog);
    const output = {
      format: FORMAT,
      schemaVersion: SCHEMA_VERSION,
      exportedAt: new Date().toISOString(),
      source: {
        url: window.location.href,
        ui5Version: window.sap?.ui?.version || null,
        toolVersion: TOOL_VERSION,
        mode: dialog.getMode?.() || null,
        themeResourceId: dialog.getThemeResourceId?.() || null,
        themeVersion: dialog.getVersion?.() ?? null,
      },
      theme: {
        colors: clone(getPreference(dialog, COLOR_PROVIDER_ID)),
        palettes: clone(getPreference(dialog, PALETTE_PROVIDER_ID)),
      },
    };

    if (options.includeStorySettings) {
      output.storySettings = clone(
        dialog._aStoryPrefs.filter((entry) =>
          hasAncestor(providerIndex, entry.id, STORY_ROOT_ID)
        )
      );
    }

    if (options.includeWidgetSettings) {
      output.widgetSettings = clone(
        dialog._aStoryPrefs.filter((entry) =>
          hasAncestor(providerIndex, entry.id, WIDGET_ROOT_ID)
        )
      );
    }

    if (options.includeSectionSettings) {
      output.sectionSettings = clone(
        dialog._aStoryPrefs.filter((entry) =>
          hasAncestor(providerIndex, entry.id, SECTION_ROOT_ID)
        )
      );
    }

    return output;
  }

  function downloadJSON(text, fileName) {
    const blob = new Blob([text], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function exportJSON(options = {}) {
    const effectiveOptions = {
      includeStorySettings: true,
      includeWidgetSettings: true,
      includeSectionSettings: true,
      download: true,
      copyToClipboard: false,
      ...options,
    };
    const dialog = getDialog();
    const output = buildExport(dialog, effectiveOptions);
    const text = JSON.stringify(output, null, 2);
    const date = new Date().toISOString().replace(/[:.]/g, "-");
    const fileName = effectiveOptions.fileName || `sac-theme-${date}.json`;

    if (effectiveOptions.download) downloadJSON(text, fileName);

    let copiedToClipboard = false;
    if (effectiveOptions.copyToClipboard) {
      try {
        await navigator.clipboard.writeText(text);
        copiedToClipboard = true;
      } catch (error) {
        console.warn("Clipboard write was blocked by the browser.", error);
      }
    }

    console.log("SAC theme JSON", output);
    return {
      data: output,
      text,
      downloaded: Boolean(effectiveOptions.download),
      copiedToClipboard,
      fileName: effectiveOptions.download ? fileName : null,
    };
  }

  function parsePayload(input) {
    const payload = typeof input === "string" ? JSON.parse(input) : clone(input);

    if (!payload || typeof payload !== "object") {
      throw new TypeError("Theme JSON must be an object or a JSON string.");
    }
    if (payload.format !== FORMAT || payload.schemaVersion !== SCHEMA_VERSION) {
      throw new Error(
        `Expected ${FORMAT} schema version ${SCHEMA_VERSION}. Export a fresh file with this tool.`
      );
    }
    if (!payload.theme?.colors || !payload.theme?.palettes) {
      throw new Error("Theme JSON is missing theme.colors or theme.palettes.");
    }
    if (payload.theme.colors.id !== COLOR_PROVIDER_ID) {
      throw new Error(`Unexpected Theme Colors id: ${payload.theme.colors.id}`);
    }
    if (payload.theme.palettes.id !== PALETTE_PROVIDER_ID) {
      throw new Error(
        `Unexpected Theme Palettes id: ${payload.theme.palettes.id}`
      );
    }

    return payload;
  }

  function getSingleSetting(preference, expectedType) {
    const setting = preference.preferences?.find(
      (candidate) => candidate.type === expectedType
    );
    if (!setting?.settings) {
      throw new Error(`Theme JSON is missing setting ${expectedType}.`);
    }
    return setting;
  }

  function validateColors(colorSetting) {
    const swatches = colorSetting.settings?.swatches?.values;
    if (!Array.isArray(swatches) || swatches.length === 0) {
      throw new Error("Theme Colors must contain settings.swatches.values.");
    }

    const ids = new Set();
    for (const swatch of swatches) {
      if (!swatch?.id || typeof swatch.baseColor !== "string") {
        throw new Error("Every theme color needs an id and baseColor.");
      }
      if (ids.has(swatch.id)) {
        throw new Error(`Duplicate theme color id: ${swatch.id}`);
      }
      ids.add(swatch.id);
      if (
        swatch.baseColor !== "transparent" &&
        !CSS.supports("color", swatch.baseColor)
      ) {
        throw new Error(
          `Invalid CSS color for ${swatch.id}: ${swatch.baseColor}`
        );
      }
    }

    return ids;
  }

  function validatePalettes(paletteSetting, swatchIds) {
    const palettes = paletteSetting.settings?.palettes;
    if (!palettes || typeof palettes !== "object") {
      throw new Error("Theme Palettes must contain settings.palettes.");
    }

    const warnings = [];
    const visit = (value, path = "palettes") => {
      if (Array.isArray(value)) {
        value.forEach((item, index) => visit(item, `${path}[${index}]`));
        return;
      }
      if (!value || typeof value !== "object") return;

      for (const [key, child] of Object.entries(value)) {
        const childPath = `${path}.${key}`;
        if (/SwatchId$/.test(key) && typeof child === "string") {
          if (!swatchIds.has(child)) warnings.push(`${childPath}: ${child}`);
        } else if (key === "swatchIds") {
          const values = Array.isArray(child)
            ? child
            : child && typeof child === "object"
              ? Object.values(child)
              : [];
          for (const id of values) {
            if (typeof id === "string" && !swatchIds.has(id)) {
              warnings.push(`${childPath}: ${id}`);
            }
          }
        }
        visit(child, childPath);
      }
    };

    visit(palettes);
    return warnings;
  }

  function updatePaletteSetting(dialog, incomingPreference) {
    const provider = getProvider(dialog, PALETTE_PROVIDER_ID);
    const control = provider._aSettingControls?.[0];
    const incomingSetting = getSingleSetting(
      incomingPreference,
      "sap.epm.appBuilding.settings.palette"
    );

    if (!control?.setProperty || !control?.syncExternalSettingsToModel) {
      throw new Error("SAC Theme Palettes control is not available in this build.");
    }

    const before = JSON.stringify(provider._aSettings?.[0]?.settings?.palettes);
    control.setProperty("settings", clone(incomingSetting), true);
    control.renderPaletteSections?.();
    control.syncExternalSettingsToModel();
    const after = JSON.stringify(provider._aSettings?.[0]?.settings?.palettes);
    return before !== after;
  }

  function updateColorSetting(dialog, incomingPreference) {
    const provider = getProvider(dialog, COLOR_PROVIDER_ID);
    const control = provider._aSettingControls?.[0];
    const section = control?._themeColorSection;
    const incomingSetting = getSingleSetting(
      incomingPreference,
      "sap.epm.appBuilding.settings.color"
    );
    const currentSetting = provider._aSettings?.find(
      (candidate) => candidate.type === "sap.epm.appBuilding.settings.color"
    );

    if (!control?.setProperty || !control?.fireSettingChanged || !currentSetting) {
      throw new Error("SAC Theme Colors control is not available in this build.");
    }

    const nextSetting = clone(currentSetting);
    const currentById = new Map(
      nextSetting.settings.swatches.values.map((swatch) => [swatch.id, swatch])
    );
    const changedIds = [];
    const unknownIds = [];

    for (const incoming of incomingSetting.settings.swatches.values) {
      const current = currentById.get(incoming.id);
      if (!current) {
        unknownIds.push(incoming.id);
        continue;
      }

      const before = JSON.stringify(current);
      Object.assign(current, clone(incoming));
      if (JSON.stringify(current) !== before) changedIds.push(incoming.id);
    }

    if (changedIds.length > 0) {
      control.setProperty("settings", nextSetting, true);
      section?.setProperty?.(
        "colorSwatches",
        nextSetting.settings.swatches.values,
        true
      );
      section?.renderReactComponent?.();
      control.fireSettingChanged({
        type: nextSetting.type,
        settings: { swatches: clone(nextSetting.settings.swatches) },
      });
    }

    return { changedIds, unknownIds };
  }

  function prepareAdditionalImports(dialog, payload, options) {
    const providerIndex = buildProviderIndex(dialog);
    const warnings = [];
    const configurations = [
      { name: "story", option: "applyStorySettings", payloadKey: "storySettings", rootId: STORY_ROOT_ID },
      { name: "widget", option: "applyWidgetSettings", payloadKey: "widgetSettings", rootId: WIDGET_ROOT_ID },
      { name: "section", option: "applySectionSettings", payloadKey: "sectionSettings", rootId: SECTION_ROOT_ID },
    ];
    const groups = {};

    for (const configuration of configurations) {
      if (!options[configuration.option]) {
        groups[configuration.name] = [];
        continue;
      }

      let entries = payload[configuration.payloadKey];

      // Version 1.0 exports included Section settings in widgetSettings.
      if (
        configuration.name === "section" &&
        !Array.isArray(entries) &&
        Array.isArray(payload.widgetSettings)
      ) {
        entries = payload.widgetSettings.filter((entry) =>
          hasAncestor(providerIndex, entry.id, SECTION_ROOT_ID)
        );
      }

      if (!Array.isArray(entries)) {
        throw new Error(
          `Import option ${configuration.option} requires ${configuration.payloadKey}. ` +
            "Export a new JSON file with the corresponding include option."
        );
      }

      groups[configuration.name] = entries.filter((entry) => {
        if (!entry?.id || !Array.isArray(entry.preferences)) {
          warnings.push(`${configuration.payloadKey}: skipped an invalid preference entry.`);
          return false;
        }
        if (!hasAncestor(providerIndex, entry.id, configuration.rootId)) {
          warnings.push(`${configuration.payloadKey}: skipped out-of-group provider ${entry.id}.`);
          return false;
        }
        if (!providerIndex.has(entry.id)) {
          warnings.push(`${configuration.payloadKey}: provider is unavailable in this SAC build: ${entry.id}.`);
          return false;
        }
        return true;
      });
    }

    return { groups, warnings };
  }

  function applyAdditionalImports(dialog, prepared) {
    const changed = { story: [], widget: [], section: [] };
    const warnings = [...prepared.warnings];

    for (const [groupName, entries] of Object.entries(prepared.groups)) {
      for (const entry of entries) {
        const provider = getProvider(dialog, entry.id);

        for (const incomingSetting of entry.preferences) {
          if (!incomingSetting?.type || !incomingSetting.settings) {
            warnings.push(`${entry.id}: skipped an invalid setting entry.`);
            continue;
          }

          const currentSetting = provider._aSettings?.find(
            (candidate) => candidate.type === incomingSetting.type
          );

          if (!currentSetting) {
            warnings.push(`${entry.id}: setting is unavailable in this SAC build: ${incomingSetting.type}.`);
            continue;
          }

          if (JSON.stringify(currentSetting.settings) === JSON.stringify(incomingSetting.settings)) {
            continue;
          }

          if (typeof provider._onSettingChanged !== "function") {
            warnings.push(
              `${entry.id}: provider cannot update setting in this SAC build: ${incomingSetting.type}.`
            );
            continue;
          }

          const nextSetting = {
            ...clone(currentSetting),
            settings: clone(incomingSetting.settings),
          };
          const eventParameters = {
            type: nextSetting.type,
            settings: clone(nextSetting.settings),
          };

          try {
            // Call the provider's normal model-update handler directly. Firing
            // the control event also invokes SAC preview listeners; for controls
            // outside the visible category, those listeners may have no mounted
            // preview document and can throw while reading getElementById().
            provider._onSettingChanged({
              getParameter: (name) => eventParameters[name],
              getParameters: () => eventParameters,
            });
          } catch (error) {
            warnings.push(
              `${entry.id}: failed to update ${incomingSetting.type}: ${error.message || error}`
            );
            continue;
          }

          const updatedSetting = provider._aSettings?.find(
            (candidate) => candidate.type === incomingSetting.type
          );
          if (
            JSON.stringify(updatedSetting?.settings) !==
            JSON.stringify(nextSetting.settings)
          ) {
            warnings.push(
              `${entry.id}: SAC did not accept setting ${incomingSetting.type}.`
            );
            continue;
          }

          // Keep the backing property synchronized without invoking setSettings(),
          // which rebuilds child controls in some SAC editors.
          const control = provider._aSettingControls?.find(
            (candidate) => candidate.getSettings?.()?.type === incomingSetting.type
          );
          control?.setProperty?.("settings", clone(updatedSetting), true);

          changed[groupName].push({
            providerId: entry.id,
            settingType: nextSetting.type,
          });
        }
      }
    }

    return { changed, warnings };
  }

  async function applyJSON(input, options = {}) {
    const effectiveOptions = {
      save: false,
      dryRun: false,
      applyStorySettings: false,
      applyWidgetSettings: false,
      applySectionSettings: false,
      ...options,
    };
    const dialog = getDialog();
    const payload = parsePayload(input);
    const colorSetting = getSingleSetting(
      payload.theme.colors,
      "sap.epm.appBuilding.settings.color"
    );
    const paletteSetting = getSingleSetting(
      payload.theme.palettes,
      "sap.epm.appBuilding.settings.palette"
    );
    const colorIds = validateColors(colorSetting);
    const paletteWarnings = validatePalettes(paletteSetting, colorIds);

    const currentColorIds = new Set(
      getSingleSetting(
        getPreference(dialog, COLOR_PROVIDER_ID),
        "sap.epm.appBuilding.settings.color"
      ).settings.swatches.values.map((swatch) => swatch.id)
    );
    const unknownColorIds = [...colorIds].filter((id) => !currentColorIds.has(id));
    const preparedAdditional = prepareAdditionalImports(
      dialog,
      payload,
      effectiveOptions
    );

    if (effectiveOptions.dryRun) {
      return {
        valid: true,
        applied: false,
        paletteReferenceWarnings: paletteWarnings,
        unknownColorIds,
        additionalSettings: {
          story: { requested: effectiveOptions.applyStorySettings, entryCount: preparedAdditional.groups.story.length },
          widget: { requested: effectiveOptions.applyWidgetSettings, entryCount: preparedAdditional.groups.widget.length },
          section: { requested: effectiveOptions.applySectionSettings, entryCount: preparedAdditional.groups.section.length },
        },
        additionalSettingsWarnings: preparedAdditional.warnings,
      };
    }

    // Apply palettes first. The subsequent Theme Colors event lets SAC update
    // every literal value that is linked to a named color swatch.
    const palettesChanged = updatePaletteSetting(dialog, payload.theme.palettes);
    const additionalResult = applyAdditionalImports(dialog, preparedAdditional);
    const colorResult = updateColorSetting(dialog, payload.theme.colors);

    // Theme Colors are applied last so SAC can refresh literal colors in every
    // imported Story, Widget, and Section setting that references a named swatch.
    // SAC's named-color propagation is scheduled from a setting-change event.
    await wait(150);

    let saveRequested = false;
    if (effectiveOptions.save) {
      if (typeof dialog._onSaveButtonPress !== "function") {
        throw new Error("The SAC Theme Preferences Save action was not found.");
      }
      dialog._onSaveButtonPress();
      saveRequested = true;
    }

    const result = {
      valid: true,
      applied: true,
      colorsChanged: colorResult.changedIds,
      palettesChanged,
      storySettingsChanged: additionalResult.changed.story,
      widgetSettingsChanged: additionalResult.changed.widget,
      sectionSettingsChanged: additionalResult.changed.section,
      paletteReferenceWarnings: paletteWarnings,
      additionalSettingsWarnings: additionalResult.warnings,
      unknownColorIds: [...new Set([...unknownColorIds, ...colorResult.unknownIds])],
      saveRequested,
      message: effectiveOptions.save
        ? "Settings applied; SAC Save was invoked. Complete any confirmation shown by SAC."
        : "Settings applied to the open dialog. Additional setting controls may redraw only after Save and reopen.",
    };

    console.log("SAC theme import result", result);
    return result;
  }

  function chooseJSONFile() {
    return new Promise((resolve, reject) => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".json,application/json";
      input.style.display = "none";
      input.addEventListener(
        "change",
        async () => {
          try {
            const file = input.files?.[0];
            if (!file) {
              reject(new Error("No JSON file was selected."));
              return;
            }
            resolve({ fileName: file.name, text: await file.text() });
          } catch (error) {
            reject(error);
          } finally {
            input.remove();
          }
        },
        { once: true }
      );
      document.body.appendChild(input);
      input.click();
    });
  }

  async function applyFromFile(options = {}) {
    const file = await chooseJSONFile();
    const result = await applyJSON(file.text, options);
    return { ...result, fileName: file.fileName };
  }

  function inspect() {
    const dialog = getDialog();
    const providerIndex = buildProviderIndex(dialog);
    return {
      dialogClass: dialog.getMetadata().getName(),
      mode: dialog.getMode?.(),
      preferenceCount: dialog._aStoryPrefs.length,
      providers: [...providerIndex.values()],
    };
  }

  const api = Object.freeze({
    version: TOOL_VERSION,
    exportJSON,
    applyJSON,
    applyFromFile,
    inspect,
  });

  Object.defineProperty(window, "SACThemeTools", {
    configurable: true,
    enumerable: false,
    writable: false,
    value: api,
  });

  console.info(
    `SACThemeTools ${TOOL_VERSION} installed. Run await SACThemeTools.exportJSON().`
  );
  return api;
})();
