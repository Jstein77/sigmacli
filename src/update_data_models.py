#!/usr/bin/env python3
"""
Script to detect changes to data model YAML files and update them via Sigma's API.
Compares local YAML files against the published version from the API to determine changes.
This script only handles updating existing data models, not creating new ones. 
"""

import sys
import argparse
from pathlib import Path
import yaml
from sigma_client import SigmaClient


def get_published_versions(client: SigmaClient, data_model_id: str):
    """
    Fetch version info of a published data model from the API.
    Returns (version_info, exists) tuple where version_info contains documentVersion and schemaVersion.
    """
    endpoint = f'/v3alpha/datamodels/{data_model_id}/spec'
    response = client.get_raw(endpoint)

    if response.status_code == 200:
        spec = response.json()
        version_info = {
            'documentVersion': spec.get('documentVersion'),
            'schemaVersion': spec.get('schemaVersion')
        }
        return version_info, True
    else:
        return None, False


def versions_match(local_spec: dict, published_versions: dict, debug: bool = False, file_name: str = "") -> bool:
    """
    Compare documentVersion and schemaVersion between local and published specs.
    Returns True if versions match (no update needed).
    """
    local_doc_version = local_spec.get('documentVersion')
    local_schema_version = local_spec.get('schemaVersion')

    published_doc_version = published_versions.get('documentVersion')
    published_schema_version = published_versions.get('schemaVersion')

    versions_match = (
        local_doc_version == published_doc_version and
        local_schema_version == published_schema_version
    )

    if debug and not versions_match:
        print(f"\n  {file_name}: Version mismatch detected")
        print(f"    documentVersion:  LOCAL={local_doc_version}, PUBLISHED={published_doc_version}")
        print(f"    schemaVersion:    LOCAL={local_schema_version}, PUBLISHED={published_schema_version}")

    return versions_match


def get_changed_yaml_files(client: SigmaClient, data_models_dir: Path, debug: bool = True):
    """
    Get list of YAML files that differ from their published versions.
    Compares documentVersion and schemaVersion between local and published versions.
    Returns list of tuples: (filepath, is_new)
    If debug=True, prints version differences for each changed file.
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

            # Get published version info
            published_versions, exists = get_published_versions(client, data_model_id)

            if not exists:
                # New data model
                if debug:
                    print(f"\n  {file_path.name}: NEW data model (not published yet)")
                changed_files.append((str(file_path), True))
            elif not versions_match(local_spec, published_versions, debug=debug, file_name=file_path.name):
                # Existing data model with version changes
                changed_files.append((str(file_path), False))
            else:
                # No changes, skip
                if debug:
                    print(f"\n  {file_path.name}: Versions match, no changes detected")

        except Exception as e:
            print(f"  WARNING: Error processing {file_path.name}: {e}")
            continue

    return changed_files


def check_data_model_exists(client: SigmaClient, data_model_id: str) -> bool:
    """Check if a data model exists in Sigma."""
    _, exists = get_published_versions(client, data_model_id)
    return exists


def get_full_published_spec(client: SigmaClient, data_model_id: str):
    """Fetch the full YAML spec for a data model from Sigma."""
    endpoint = f'/v3alpha/datamodels/{data_model_id}/spec'
    response = client.get_raw(endpoint)

    if response.status_code == 200:
        return response.json(), None
    else:
        error_msg = response.json() if response.text else response.reason
        return None, f"Status {response.status_code}: {error_msg}"


def sync_data_models(client: SigmaClient, data_models_dir: Path, debug: bool = True):
    """
    Sync local data model files with Sigma by pulling latest versions from API.
    Identifies changed files and overwrites them with the published version from Sigma.

    Returns: (successful_count, failed_count)
    """
    print(f"\nSyncing data models from Sigma to local directory...")
    print(f"Directory: {data_models_dir}")

    # Get changed files
    changed_files = get_changed_yaml_files(client, data_models_dir, debug=debug)

    if not changed_files:
        print("\nNo version differences detected. All files are in sync.")
        return 0, 0

    print(f"\nFound {len(changed_files)} file(s) with version differences")
    print("Pulling latest versions from Sigma...\n")

    successful = 0
    failed = 0

    for i, (filepath, is_new) in enumerate(changed_files, 1):
        file_path = Path(filepath)

        if is_new:
            print(f"[{i}/{len(changed_files)}] Skipping {file_path.name} - not published in Sigma yet")
            continue

        print(f"[{i}/{len(changed_files)}] Syncing {file_path.name}")

        try:
            # Load local file to get data model ID
            with open(file_path, 'r') as f:
                local_spec = yaml.safe_load(f)

            data_model_id = local_spec.get('dataModelId')
            if not data_model_id:
                print(f"  ERROR: No dataModelId found in {file_path.name}")
                failed += 1
                continue

            # Get full spec from Sigma
            published_spec, error = get_full_published_spec(client, data_model_id)

            if error:
                print(f"  ERROR: {error}")
                failed += 1
                continue

            # Overwrite local file with published version
            with open(file_path, 'w') as f:
                yaml.dump(published_spec, f, indent=2, sort_keys=False, default_flow_style=False)

            print(f"  ✓ Synced successfully")
            print(f"    documentVersion: {published_spec.get('documentVersion')}")
            print(f"    schemaVersion: {published_spec.get('schemaVersion')}")
            successful += 1

        except Exception as e:
            print(f"  ERROR: {str(e)}")
            failed += 1

    return successful, failed


def update_data_model(client: SigmaClient, data_model_id: str, yaml_spec: dict):
    """Update an existing data model via Sigma's API."""
    endpoint = f'/v3alpha/datamodels/{data_model_id}/spec'
    response = client.put(endpoint, yaml_spec)

    # Check response
    if response.status_code == 200:
        return response.json() if response.text else None, None
    else:
        error_msg = response.json() if response.text else response.reason
        return None, f"Status {response.status_code}: {error_msg}"


def main():
    """Main function to detect and update changed data models."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Detect and update changed data models in Sigma'
    )
    parser.add_argument(
        '--env',
        default='staging',
        help='Environment to use (default: staging)'
    )
    parser.add_argument(
        '--dir',
        default='data-models',
        help='Directory containing data model YAML files (default: data-models)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode with verbose output'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be updated without making actual changes'
    )

    args = parser.parse_args()

    print("Data ModeUpdate Script")
    print("=" * 60)
    print(f"Environment: {args.env}")
    print(f"Directory: {args.dir}")
    if args.dry_run:
        print("Mode: DRY RUN (no actual changes will be made)")
    print("=" * 60)

    # Initialize client and authenticate
    print("\nAuthenticating to Sigma...")
    client = SigmaClient(env=args.env)
    print(f"Authenticated successfully to {client.base_url}")

    # Set up data models directory
    data_models_dir = Path(args.dir)

    if not data_models_dir.exists():
        print(f"\nError: Directory '{data_models_dir}' does not exist")
        sys.exit(1)

    # Get changed files by comparing against published versions
    print(f"\nScanning for changes in {data_models_dir}...")
    print("Comparing local files against published versions...")
    changed_files = get_changed_yaml_files(client, data_models_dir, debug=args.debug)

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
            exists = check_data_model_exists(client, data_model_id)

            if args.dry_run:
                # Dry run mode - just show what would happen
                action = "update" if exists else "create"
                print(f"  [DRY RUN] Would {action} this data model")
                successful += 1
            else:
                # Actually perform the update/create
                if exists:
                    print(f"  Updating existing data model...")
                    result, error = update_data_model(client, data_model_id, yaml_spec)
                else:
                    print(f" Data model does not exist, doing nothing")

                if error:
                    print(f"  ERROR: {error}")
                    failed += 1
                else:
                    action = "Updated" if exists else "Skip"
                    print(f"  SUCCESS: {action} successfully")
                    if result and 'documentVersion' in result:
                        print(f"  Version: {result['documentVersion']}")
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
    #main()
    client = SigmaClient()
    get_changed_yaml_files(client, Path('data-models'))
     # Create client                                                                                                                               
                                                                                                      
                                                                                                                                                
  # Sync all changed files                                                                                                                      
    successful, failed = sync_data_models(                                                                                                        
        client,                                                                                                                                   
        Path('data-models'),                                                                                                                      
        debug=True  # Show version differences                                                                                                    
        )                                                                                                                                             
                                                                                                                                                
    print(f"Synced {successful} files, {failed} failed")   
