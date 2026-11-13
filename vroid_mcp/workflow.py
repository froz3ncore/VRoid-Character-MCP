"""Initialize-time guidance for reference reconstruction and layered clothing.

Adapted from shamsievartyom/VRoid-Character-MCP main (cb71a749). The existing
session, file and dress-up rules stay in server.INSTRUCTIONS; this text is appended.
"""

REFERENCE_GUIDANCE = """
Reference reconstruction and layered clothing

For reference work, treat any starting model as a baseline. Identify the biggest visible mismatches in the face, hair, and outfit. Make and render targeted edits for those mismatches before treating a checkpoint as final. Compare the baseline and saved result from matching angles, with a face close-up and an outfit view.

1. Start with get_status. Pass its model_token as expected_model. Use the disposable copy by default. With the local client, run --check-save before an editing session. Keep the source and save checkpoints to new .vroid filenames.
2. From a reference, identify the silhouette, hair, face, and outfit layers. Filter list_presets by area and category and shortlist with preview_presets. Thumbnails show a standard avatar. Judge candidates on the character using capture_review with a few matching angles. The local client's --compare renders multiple presets on one saved checkpoint. Decide shape and fit before texture detail.
   For every character creation, go through every category in the Face tab. Use the categories from list_presets(area="face") and inspect the available presets in each category. Compare the current option and shortlisted alternatives against the reference, then keep or apply the closest match, including an empty option where appropriate. After choosing, use list_parameters and set_parameters to refine the result as needed. For categories without presets, review the available controls directly. Check the combined face in a close-up and report any categories you could not inspect.
3. Read list_parameters before editing. Batch related changes with set_parameters using returned IDs, types, and ranges. Re-list after applying a preset or changing garment or hair structure. Semantic keys are labels for matching, not write IDs. Clothing shape sliders accept a native category such as Tops or InnerTop. Check affected_parameter_ids before changing shared colours.
4. Layered clothing
   - Identify the actual garments, their order from the body outward, and where each should be visible. Use separate clothing categories when the pieces can coexist. Verify active items with list_parts. For pieces that share a slot, use list_clothing_templates and add_clothing_template in the innermost garment's editor to build outward. Add Template places the new garment on top. If the outer garment is already on and needs an inner layer in the same slot, export its texture first and rebuild the stack from the inside outward.
   - Fit the silhouettes with garment parameters first. Use separate templates for pieces that need their own shape and raster layers for details on the same surface. Find each template's canvas via added_images or inspect_texture_canvas(compact=true). Export a layer or UV guide before painting, then import with the full image_id and current PNG hash.
   - For openings, make the intended area transparent across all visible raster layers of the outer garment, including any default design. Transparency reveals whatever is already underneath. Use Skin Mask only to hide skin in areas covered by clothing.
   - Close the texture editor and review the front, side, and back. Check openings, hems and cuffs for missing pieces, hidden fabric and clipping. Verify that each requested garment exists before reporting it as present, even if it is partly or fully covered.
5. Inspect the saved result. If a major mismatch remains after a trial or rollback, try another supported approach or mark the feature unfinished and report the specific blocker. Use save_as for editable .vroid files and export_vrm when requested. For local path access, capture_review(include_images=false) keeps image bytes out of the response. If an edit is unconfirmed or partially applied, inspect before retrying.
"""
