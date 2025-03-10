"""The InvenTreeBarcodePlugin validates barcodes generated by InvenTree itself. It can be used as a template for developing third-party barcode plugins.

The data format is very simple, and maps directly to database objects,
via the "id" parameter.

Parsing an InvenTree barcode simply involves validating that the
references model objects actually exist in the database.
"""

import json
import re
from typing import cast

from django.utils.translation import gettext_lazy as _

import plugin.base.barcodes.helper
from InvenTree.helpers import hash_barcode
from InvenTree.models import InvenTreeBarcodeMixin
from plugin import InvenTreePlugin
from plugin.mixins import BarcodeMixin, SettingsMixin


class InvenTreeInternalBarcodePlugin(SettingsMixin, BarcodeMixin, InvenTreePlugin):
    """Builtin BarcodePlugin for matching and generating internal barcodes."""

    NAME = 'InvenTreeBarcode'
    TITLE = _('InvenTree Barcodes')
    DESCRIPTION = _('Provides native support for barcodes')
    VERSION = '2.1.0'
    AUTHOR = _('InvenTree contributors')

    SETTINGS = {
        'INTERNAL_BARCODE_FORMAT': {
            'name': _('Internal Barcode Format'),
            'description': _('Select an internal barcode format'),
            'choices': [
                ('json', _('JSON barcodes (human readable)')),
                ('short', _('Short barcodes (space optimized)')),
            ],
            'default': 'json',
        },
        'SHORT_BARCODE_PREFIX': {
            'name': _('Short Barcode Prefix'),
            'description': _(
                'Customize the prefix used for short barcodes, may be useful for environments with multiple InvenTree instances'
            ),
            'default': 'INV-',
        },
    }

    def format_matched_response(self, label, model, instance):
        """Format a response for the scanned data."""
        return {label: instance.format_matched_response()}

    def scan(self, barcode_data):
        """Scan a barcode against this plugin.

        Here we are looking for a dict object which contains a reference to a particular InvenTree database object
        """
        # Internal Barcodes - Short Format
        # Attempt to match the barcode data against the short barcode format
        prefix = cast(str, self.get_setting('SHORT_BARCODE_PREFIX'))
        if type(barcode_data) is str and (
            m := re.match(
                f'^{re.escape(prefix)}([0-9A-Z $%*+-.\\/:]{"{2}"})(\\d+)$', barcode_data
            )
        ):
            model_type_code, pk = m.groups()

            supported_models_map = (
                plugin.base.barcodes.helper.get_supported_barcode_model_codes_map()
            )
            model = supported_models_map.get(model_type_code, None)

            if model is None:
                return None

            label = model.barcode_model_type()

            try:
                instance = model.objects.get(pk=int(pk))
                return self.format_matched_response(label, model, instance)
            except (ValueError, model.DoesNotExist):
                pass

        # Internal Barcodes - JSON Format
        # Attempt to coerce the barcode data into a dict object
        # This is the internal JSON barcode representation that InvenTree uses
        barcode_dict = None

        if type(barcode_data) is dict:
            barcode_dict = barcode_data
        elif type(barcode_data) is str:
            try:
                barcode_dict = json.loads(barcode_data)
            except json.JSONDecodeError:
                pass

        supported_models = plugin.base.barcodes.helper.get_supported_barcode_models()

        succcess_message = _('Found matching item')

        if barcode_dict is not None and type(barcode_dict) is dict:
            # Look for various matches. First good match will be returned
            for model in supported_models:
                label = model.barcode_model_type()

                if label in barcode_dict:
                    try:
                        pk = int(barcode_dict[label])
                        instance = model.objects.get(pk=pk)

                        return {
                            **self.format_matched_response(label, model, instance),
                            'success': succcess_message,
                        }
                    except (ValueError, model.DoesNotExist):
                        pass

        # External Barcodes (Linked barcodes)
        # Create hash from raw barcode data
        barcode_hash = hash_barcode(barcode_data)

        # If no "direct" hits are found, look for assigned third-party barcodes
        for model in supported_models:
            label = model.barcode_model_type()

            instance = model.lookup_barcode(barcode_hash)

            if instance is not None:
                return {
                    **self.format_matched_response(label, model, instance),
                    'success': succcess_message,
                }

    def generate(self, model_instance: InvenTreeBarcodeMixin):
        """Generate a barcode for a given model instance."""
        barcode_format = self.get_setting(
            'INTERNAL_BARCODE_FORMAT', backup_value='json'
        )

        if barcode_format == 'short':
            prefix = self.get_setting('SHORT_BARCODE_PREFIX')
            model_type_code = model_instance.barcode_model_type_code()

            return f'{prefix}{model_type_code}{model_instance.pk}'
        else:
            # Default = JSON format
            return json.dumps({model_instance.barcode_model_type(): model_instance.pk})
