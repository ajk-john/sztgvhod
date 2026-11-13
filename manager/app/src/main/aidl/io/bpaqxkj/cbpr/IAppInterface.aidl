// IAppInterface.aidl
package io.bpaqxkj.cbpr;

import android.content.pm.PackageInfo;
import rikka.parcelablelist.ParcelableListSlice;

interface IAppInterface {
    ParcelableListSlice<PackageInfo> getPackages(int flags);
}