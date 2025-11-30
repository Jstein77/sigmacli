#!/usr/bin/env python3
"""
Script to pull YAML representations of all data models from a Sigma instance.
Authenticates to Sigma, finds all data models, and saves YAML specs to data-models directory.
"""

from pathlib import Path
from sigmoid.playground import (
    ensureContext, Context, paginated, geturl, raiseErrIf
)
from functools import partial
import yaml


def get_all_data_models(ctx: Context):
    """Fetch all data models from Sigma instance."""
    url = ctx.origin + '/v2/datamodels'
    data_models = []

    for dm in paginated(partial(geturl, ctx, url)):
        data_models.append(dm)

    return data_models


def get_data_model_yaml(ctx: Context, data_model_id: str, version: int = None):
    """Fetch YAML spec for a specific data model."""
    url = ctx.origin + f'/v3alpha/datamodels/{data_model_id}/spec'

    params = {}
    if version:
        params['documentVersion'] = version

    result, err = geturl(ctx, url, **params)
    raiseErrIf(result, err)

    return result


def save_data_model_yaml(data_model, yaml_spec, output_dir: Path):
    """Save data model YAML to file."""
    # Create a safe filename from data model name
    dm_name = data_model.get('name', 'unnamed')
    dm_id = data_model.get('dataModelId', 'unknown')

    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in dm_name)
    safe_name = safe_name.replace(' ', '_')

    # Append ID to the name
    filename = f"{safe_name}_{dm_id}.yaml"
    filepath = output_dir / filename

    with open(filepath, 'w') as f:
        yaml.dump(yaml_spec, f, indent=2, sort_keys=False, default_flow_style=False)

    return filepath


def main():
    """Main function to pull all data models and save their YAML specs."""
    # Initialize context and authenticate
    print("Authenticating to Sigma...")
    ctx = ensureContext(Context())
    print(f"Authenticated successfully to {ctx.origin}")

    # Create output directory
    output_dir = Path('data-models')
    output_dir.mkdir(exist_ok=True)
    print(f"Output directory: {output_dir.absolute()}")

    # Get all data models
    print("\nFetching list of data models...")
    data_models = get_all_data_models(ctx)
    print(f"Found {len(data_models)} data models")

    # Process each data model
    successful = 0
    failed = 0

    for i, dm in enumerate(data_models, 1):
        dm_name = dm.get('name', 'unnamed')
        dm_id = dm['dataModelId']
        version = dm.get('latestVersion', 1)

        print(f"\n[{i}/{len(data_models)}] Processing: {dm_name} (ID: {dm_id}, Version: {version})")

        try:
            # Get YAML spec
            yaml_spec = get_data_model_yaml(ctx, dm_id, version)

            # Save to file
            filepath = save_data_model_yaml(dm, yaml_spec, output_dir)
            print(f"  Saved to: {filepath}")
            successful += 1

        except Exception as e:
            print(f"  ERROR: {str(e)}")
            failed += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Total data models: {len(data_models)}")
    print(f"  Successfully saved: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Output directory: {output_dir.absolute()}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
