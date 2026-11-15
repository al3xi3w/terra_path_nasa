"""Local location/date/crop access without extrapolation or implicit joins."""
import json
from pathlib import Path
import pandas as pd
from .pipeline import ROOT, digest
from .audit import extract_gpm, calendar_flags


class DataStore:
    def __init__(self,root=ROOT):
        self.root=Path(root)

    def locations(self):
        return pd.read_parquet(self.root/'data/integrated/locations.parquet')

    def observations(self, *, location_id=None, start=None, end=None, source=None, crop_id=None):
        """Return overlapping periods; end is exclusive. Crop IDs are source-namespaced."""
        filters=[]
        for col,value in [('location_id',location_id),('source',source),('crop_id',crop_id)]:
            if value is not None: filters.append((col,'==',value))
        if start is not None:filters.append(('period_end_exclusive','>',str(pd.Timestamp(start).date())))
        if end is not None:filters.append(('period_start','<',str(pd.Timestamp(end).date())))
        if start and end and pd.Timestamp(start)>=pd.Timestamp(end):raise ValueError('start must precede end')
        return pd.read_parquet(self.root/'data/integrated/observations.parquet',filters=filters or None)

    def at_point(self, latitude, longitude, **filters):
        """Only exact registered coordinates. No nearest-pilot or county assignment."""
        locations=self.locations()
        matching=locations.loc[(locations.latitude==latitude)&(locations.longitude==longitude),'location_id']
        frames=[self.observations(location_id=key,**filters) for key in matching]
        return pd.concat(frames,ignore_index=True) if frames else self.observations(**filters).iloc[:0]

    def gpm_at_point(self, latitude, longitude, start=None, end=None):
        """On-demand scalar HDF5 reads from validated monthly originals, with hash check."""
        if not (-90<=latitude<=90 and -180<=longitude<180):raise ValueError('Invalid query coordinates')
        if start and end and pd.Timestamp(start)>=pd.Timestamp(end):raise ValueError('start must precede end')
        index=pd.read_parquet(self.root/'data/processed/gpm_monthly_index.parquet')
        index=index[index.status.eq('validated')]
        if index.month.duplicated().any():raise ValueError('Ambiguous monthly index')
        rows=[]
        for _,r in index.iterrows():
            if start and pd.Timestamp(r.end_exclusive)<=pd.to_datetime(start,utc=True):continue
            if end and pd.Timestamp(r.start)>=pd.to_datetime(end,utc=True):continue
            path=self.root/r.path
            if digest(path)!=r.sha256:raise ValueError('Original changed since audit')
            report=dict(status='validated',path=r.path,sha256=r.sha256,start=r.start,
                        end_exclusive=r.end_exclusive,duration_hours=r.duration_hours)
            rows.extend(extract_gpm(path,[dict(location_id='query',latitude=latitude,longitude=longitude)],report))
        return pd.DataFrame(rows)

    def crop_reference(self, source, crop, *, area=None, year=None):
        """Exact native crop identifiers/labels, preserving all variants and source columns.

        faostat: Item Code + optional Area Code/year; calendar: crop_id + required ISO country;
        ecocrop: scientificname; fao56: crop_label. No taxonomic equivalence is inferred.
        """
        if source=='calendar':
            if area is None or not str(area).isalpha() or len(area)!=2:raise ValueError('Country ISO2 required')
            path=self.root/f'data/processed/agronomy-calendar-{area.upper()}.parquet';column='crop_id'
        else:
            mapping={'faostat':('faostat_yield_global.parquet','Item Code'),
                     'ecocrop':('ecocrop_validated.parquet','scientificname'),
                     'fao56':('fao56_kc_verified.parquet','crop_label')}
            if source not in mapping:raise ValueError('Unsupported crop source')
            name,column=mapping[source];path=self.root/'data/processed'/name
        if not path.exists():return pd.DataFrame()
        entries=self._verified_lineage(path)
        filters=[(column,'==',str(crop))]
        if source=='faostat':
            if area is not None:filters.append(('Area Code','==',str(area)))
            if year is not None:filters.append(('Year','==',str(year)))
        elif year is not None:raise ValueError('Reference is not annual observations')
        result=pd.read_parquet(path,filters=filters)
        if source=='calendar':result=calendar_flags(result)
        result.attrs['fieldshift_lineage']=[json.loads(v) for v in entries.metadata_json]
        return result

    def _verified_lineage(self, path):
        """Fail closed when the latest lineage audit marks a processed table untrusted."""
        catalog=pd.read_parquet(self.root/'data/integrated/catalog.parquet')
        entries=catalog[catalog.processed.eq(str(Path(path).relative_to(self.root)))]
        if entries.empty or not entries.status.eq('verified').all():raise ValueError('Reference lineage not verified')
        for value in entries.metadata_json:
            meta=json.loads(value)
            if digest(self.root/meta['path'])!=meta['sha256'] or digest(path)!=meta['output_sha256']:
                raise ValueError('Reference changed since audit')
        return entries

    def verified_table(self, relative):
        """Whole processed reference table after the same lineage check as crop_reference."""
        path=self.root/relative
        entries=self._verified_lineage(path)
        result=pd.read_parquet(path)
        result.attrs['fieldshift_lineage']=[json.loads(v) for v in entries.metadata_json]
        result.attrs['sha256']=digest(path)
        return result
