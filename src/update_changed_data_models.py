#!/usr/bin/env python3
"""
Script to detect changes to data model YAML files and create/update them via Sigma's API.
Compares local YAML files against the published version from the API to determine changes.
New data models are created via POST, existing ones are updated via PUT.
"""

import sys
from pathlib import Path
from sigmoid.playground import (
    ensureContext, Context, putraw, postraw, raiseErrIf, geturl
)
import yaml


def get_published_data_model(ctx: Context, data_model_id: str):
    """
    Fetch the published version of a data model from the API.
    Returns (yaml_spec, exists) tuple where exists is True if the model exists.
    """
    url = ctx.origin + f'/v3alpha/datamodels/{data_model_id}/spec'
    result, err = geturl(ctx, url)

    # If we get a 200, the data model exists
    if err == 200:
        return result, True
    else:
        return None, False


def specs_are_equal(local_spec: dict, published_spec: dict, debug: bool = False, file_name: str = "") -> bool:
    """
    Compare two data model specs to determine if they are equal.
    Ignores fields that are managed by the server.
    If debug=True, prints detailed differences between specs.
    """
    # Fields to ignore in comparison (server-managed fields)
    ignore_fields = {'id', 'documentVersion', 'lastModified', 'createdAt', 'updatedAt'}

    # Create copies without ignored fields
    local_filtered = {k: v for k, v in local_spec.items() if k not in ignore_fields}
    published_filtered = {k: v for k, v in published_spec.items() if k not in ignore_fields}

    are_equal = local_filtered == published_filtered

    # If debug mode and specs differ, show what's different
    if debug and not are_equal:
        print(f"\n  === DIFFERENCES FOUND in {file_name} ===")

        # Get all keys from both specs
        all_keys = set(local_filtered.keys()) | set(published_filtered.keys())

        for key in sorted(all_keys):
            local_val = local_filtered.get(key)
            published_val = published_filtered.get(key)

            if key not in local_filtered:
                print(f"    [{key}]")
                print(f"      - Only in PUBLISHED: {published_val}")
            elif key not in published_filtered:
                print(f"    [{key}]")
                print(f"      - Only in LOCAL: {local_val}")
            elif local_val != published_val:
                print(f"    [{key}]")
                print(f"      - LOCAL:     {local_val}")
                print(f"      - PUBLISHED: {published_val}")

        print(f"  === END DIFFERENCES ===\n")

    return are_equal


def get_changed_yaml_files(ctx: Context, data_models_dir: Path, debug: bool = True):
    """
    Get list of YAML files that differ from their published versions.
    Compares local files against the published API versions.
    Returns list of tuples: (filepath, is_new)
    If debug=True, prints detailed differences for each changed file.
    """
    changed_files = []

    # Get all YAML files in the directory
    yaml_files = list(data_models_dir.glob('*.yaml')) + list(data_models_dir.glob('*.yml'))

    for file_path in yaml_files:
        try:
            # Load local YAML file
            with open(file_path, 'r') as f:
                local_spec = yaml.safe_load(f)

            # Extract data model ID
            if 'dataModelId' not in local_spec:
                print(f"  WARNING: Skipping {file_path.name} - no dataModelId found")
                continue

            data_model_id = local_spec['dataModelId']

            # Get published version
            published_spec, exists = get_published_data_model(ctx, data_model_id)

            if not exists:
                # New data model
                if debug:
                    print(f"\n  {file_path.name}: NEW data model (not published yet)")
                changed_files.append((str(file_path), True))
            elif not specs_are_equal(local_spec, published_spec, debug=debug, file_name=file_path.name):
                # Existing data model with changes
                changed_files.append((str(file_path), False))
            else:
                # No changes, skip
                if debug:
                    print(f"\n  {file_path.name}: No changes detected")

        except Exception as e:
            print(f"  WARNING: Error processing {file_path.name}: {e}")
            continue

    return changed_files


def check_data_model_exists(ctx: Context, data_model_id: str) -> bool:
    """Check if a data model exists in Sigma."""
    _, exists = get_published_data_model(ctx, data_model_id)
    return exists


def create_data_model(ctx: Context, yaml_spec: dict):
    """Create a new data model via Sigma's API."""
    url = ctx.origin + '/v3alpha/datamodels/spec'

    result = postraw(ctx, url, yaml_spec)

    # Check response
    if result.status_code == 200:
        return result.json() if result.text else None, None
    else:
        error_msg = result.json() if result.text else result.reason
        return None, f"Status {result.status_code}: {error_msg}"


def update_data_model(ctx: Context, data_model_id: str, yaml_spec: dict):
    """Update an existing data model via Sigma's API."""
    url = ctx.origin + f'/v3alpha/datamodels/{data_model_id}/spec'

    result = putraw(ctx, url, yaml_spec)

    # Check response
    if result.status_code == 200:
        return result.json() if result.text else None, None
    else:
        error_msg = result.json() if result.text else result.reason
        return None, f"Status {result.status_code}: {error_msg}"


def main():
    """Main function to detect and create/update changed data models."""
    print("Data Model Create/Update Script")
    print("=" * 60)

    # Initialize context and authenticate
    print("\nAuthenticating to Sigma...")
    ctx = ensureContext(Context())
    print(f"Authenticated successfully to {ctx.origin}")

    # Set up data models directory
    data_models_dir = Path('data-models')

    if not data_models_dir.exists():
        print(f"\nError: Directory '{data_models_dir}' does not exist")
        sys.exit(1)

    # Get changed files by comparing against published versions
    print(f"\nScanning for changes in {data_models_dir}...")
    print("Comparing local files against published versions...")
    changed_files = get_changed_yaml_files(ctx, data_models_dir)

    if not changed_files:
        print("No changes detected in data model files.")
        print("\nNothing to create or update.")
        return

    print(f"Found {len(changed_files)} changed file(s):")
    for f, is_new in changed_files:
        status = "NEW" if is_new else "MODIFIED"
        print(f"  - {f} [{status}]")

    # Process each changed file
    print("\n" + "=" * 60)
    successful = 0
    failed = 0
    skipped = 0

    for i, (filepath, is_new) in enumerate(changed_files, 1):
        file_path = Path(filepath)

        if not file_path.exists():
            print(f"\n[{i}/{len(changed_files)}] Skipping deleted file: {filepath}")
            skipped += 1
            continue

        status = "NEW" if is_new else "MODIFIED"
        print(f"\n[{i}/{len(changed_files)}] Processing: {filepath} [{status}]")

        try:
            # Load YAML file
            with open(file_path, 'r') as f:
                yaml_spec = yaml.safe_load(f)

            # Extract data model ID
            if 'dataModelId' not in yaml_spec:
                print(f"  ERROR: No 'dataModelId' found in {filepath}")
                failed += 1
                continue

            data_model_id = yaml_spec['dataModelId']
            data_model_name = yaml_spec.get('name', 'unknown')

            print(f"  Data Model: {data_model_name}")
            print(f"  ID: {data_model_id}")

            # Check if data model exists
            exists = check_data_model_exists(ctx, data_model_id)

            if exists:
                print(f"  Updating existing data model...")
                result, error = update_data_model(ctx, data_model_id, yaml_spec)
            else:
                print(f"  Creating new data model...")
                result, error = create_data_model(ctx, yaml_spec)

            if error:
                print(f"  ERROR: {error}")
                failed += 1
            else:
                action = "Updated" if exists else "Created"
                print(f"  SUCCESS: {action} successfully")
                if result and 'documentVersion' in result:
                    print(f"  Version: {result['documentVersion']}")

                # For new data models, update the file with the actual ID from the response
                if not exists and result and 'dataModelId' in result:
                    actual_id = result['dataModelId']
                    print(f"  Updating file with actual data model ID: {actual_id}")

                    # Update the YAML spec with the actual ID
                    yaml_spec['dataModelId'] = actual_id

                    # Also update other fields returned from the server
                    for key in ['url', 'documentVersion', 'latestDocumentVersion', 'schemaVersion',
                                'ownerId', 'folderId', 'createdBy', 'updatedBy', 'createdAt', 'updatedAt']:
                        if key in result:
                            yaml_spec[key] = result[key]

                    # Write the updated spec back to the file
                    with open(file_path, 'w') as f:
                        yaml.dump(yaml_spec, f, indent=2, sort_keys=False, default_flow_style=False)

                    print(f"  Updated {file_path.name} with server-assigned ID and metadata")

                successful += 1

        except Exception as e:
            print(f"  ERROR: {str(e)}")
            failed += 1

    # Summary
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total files processed: {len(changed_files)}")
    print(f"  Successfully created/updated: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Skipped: {skipped}")
    print("=" * 60)

    # Exit with error code if any failed
    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
